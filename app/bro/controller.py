"""Copyright (c) 2023 VIKTOR B.V.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

VIKTOR B.V. PROVIDES THIS SOFTWARE ON AN "AS IS" BASIS, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO EVENT
SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import json
from datetime import datetime

# pylint: disable=line-too-long, c-extension-no-member
from math import floor
from pathlib import Path
from typing import List
from typing import Optional

import geopandas as gpd
from bro import Envelope
from bro import Point
from bro import get_cpt_characteristics
from bro import get_cpt_object
from plotly import graph_objects as go
from plotly.subplots import make_subplots
from requests import ReadTimeout

from viktor import Color
from viktor import File
from viktor import UserError
from viktor import ViktorController
from viktor.core import progress_message
from viktor.geometry import GeoPolygon
from viktor.result import DownloadResult
from viktor.result import SetParamsResult
from viktor.views import InteractionEvent
from viktor.views import MapLabel
from viktor.views import MapLegend
from viktor.views import MapPoint
from viktor.views import MapPolygon
from viktor.views import MapPolyline
from viktor.views import MapResult
from viktor.views import MapView
from viktor.views import PlotlyResult
from viktor.views import PlotlyView
from viktor.views import WebResult
from viktor.views import WebView

from .bro_api import filter_available_cpts
from .bro_api import get_cpt_object_xml_async
from .classification import CPT
from .classification import Classification
from .classification import IMBROFile
from .parametrization import DEFAULT_ROBERTSON_TABLE
from .parametrization import Parametrization

MAX_AMOUNT_OF_CPTS = 15


class Controller(ViktorController):
    label = "BRO CPT retriever"
    parametrization = Parametrization(width=30)

    @MapView("Locations", duration_guess=1)
    def view_locations_step_1(self, params, **kwargs) -> MapResult:
        """
        Viewer that shows the following:
        - Selected polygon
        - Available CPTs
        - Selected CPTs
        - Boundary of NL (BRO availability zone)
        """
        features, labels = [], []

        nl_boundary = self.get_nl_boundary_map_features()
        features.append(nl_boundary)

        if params.step_1.geo_polygon:
            features.append(MapPolygon.from_geo_polygon(params.step_1.geo_polygon, color=Color.red()))

        interaction_cpts = []
        if params.retrieved_cpts:
            filtered_cpts = json.loads(params["retrieved_cpts"])["cpt_ids"]
            for cpt in filtered_cpts:
                color = (
                    Color.viktor_yellow()
                    if cpt["bro_id"] in params.step_2.signals_selected_cpts
                    else Color.viktor_blue()
                )
                point = MapPoint(
                    float(cpt["lat"]),
                    float(cpt["lon"]),
                    title=cpt["bro_id"],
                    description=f"CPT performed at: {cpt['date']}  \n",
                    color=color,
                    identifier=cpt["bro_id"],
                    icon="triangle-down-filled",
                )
                if params.step_1.show_labels:
                    label = MapLabel(
                        float(cpt["lat"]),
                        float(cpt["lon"]),
                        text=cpt["bro_id"],
                        scale=20.5 - params.step_1.label_size * 0.5,
                    )
                    labels.append(label)
                features.append(point)
                interaction_cpts.append(point)

        interaction_groups = {
            "points": interaction_cpts,
        }

        legend = MapLegend(
            [
                (Color.viktor_blue(), "Available CPTs"),
                (Color.viktor_yellow(), "Selected CPTs"),
                (Color.black(), "BRO availability zone"),
            ]
        )
        return MapResult(
            features=features,
            labels=labels,
            interaction_groups=interaction_groups,
            legend=legend,
        )

    @PlotlyView("CPT comparison", duration_guess=5, update_label="Show CPT comparison")
    def visualize_cpt_comparison(self, params, **kwargs) -> PlotlyResult:
        """
        Visualizes the Robertson classification of the selected CPTs.
        """
        cpt_ids = params.step_2.signals_selected_cpts
        if not cpt_ids:
            raise UserError("Please select CPTs for comparison")

        if len(cpt_ids) > 10:
            raise UserError("Please select no more than 10 CPTs to compare.")

        soil_mapping = Classification(DEFAULT_ROBERTSON_TABLE).soil_mapping
        progress_message("Gathering CPTs to add to comparison")

        xml_files = [get_cpt_object(bro_cpt_id) for bro_cpt_id in cpt_ids]
        cpt_dicts = [IMBROFile(xml_file_content) for xml_file_content in xml_files]
        # Classify
        classified_cpts = [Classification(DEFAULT_ROBERTSON_TABLE).classify_cpt_file(cpt) for cpt in cpt_dicts]
        cpts = [CPT(cpt_params=classified_cpt, soil_mapping=soil_mapping) for classified_cpt in classified_cpts]

        figure = visualize_cpts_with_classifications(cpts)
        return PlotlyResult(figure)

    @WebView(" ", duration_guess=1)
    def final_step(self, params, **kwargs):
        """Initiates the process of rendering the last step."""
        html_path = Path(__file__).parent / "final_step.html"
        with html_path.open(encoding="utf-8") as _file:
            html_string = _file.read()
        return WebResult(html=html_string)

    @staticmethod
    def download_selected_cpts_from_bro(params, **kwargs) -> DownloadResult:
        """
        Downloads the selected CPTs in XML format.
        """
        cpt_ids = params.step_2.signals_selected_cpts
        xml_bytes = []
        for chunk in splitter(
            cpt_ids, MAX_AMOUNT_OF_CPTS
        ):  # to prevent overflowing of client, split async requests up in smaller parts
            xml_bytes += [xml_str.encode("utf-8") for xml_str in get_cpt_object_xml_async(chunk)]

        zipped_files = {}
        for cpt_id, xml in zip(cpt_ids, xml_bytes):
            zipped_files[f"{cpt_id}.xml"] = File.from_data(xml)
        return DownloadResult(zipped_files=zipped_files, file_name="CPTs_in_bounding_box.zip")

    @staticmethod
    def download_all_cpts_from_bro(params, **kwargs) -> DownloadResult:
        """
        Downloads the all available CPTs in the selected area in XML format.
        """
        cpt_ids = [cpt["bro_id"] for cpt in json.loads(params["retrieved_cpts"])["cpt_ids"]]

        xml_bytes = []
        for chunk in splitter(
            cpt_ids, MAX_AMOUNT_OF_CPTS
        ):  # to prevent overflowing of client, split async requests up in smaller parts
            xml_bytes += [xml_str.encode("utf-8") for xml_str in get_cpt_object_xml_async(chunk)]

        zipped_files = {}
        for cpt_id, xml in zip(cpt_ids, xml_bytes):
            zipped_files[f"{cpt_id}.xml"] = File.from_data(xml)
        return DownloadResult(zipped_files=zipped_files, file_name="CPTs_in_bounding_box.zip")

    @staticmethod
    def select_from_map(event: Optional[InteractionEvent], **kwargs) -> SetParamsResult:
        """
        Sets the "signals_selected_cpts" field in the parametrization based on MapInteraction.
        """
        updated_params = {}
        if event:
            cpt_ids = event.value
            if not cpt_ids:
                raise UserError("Please select CPTs for comparison")
            updated_params = {"step_2": {"signals_selected_cpts": cpt_ids}}
        return SetParamsResult(updated_params)

    def retrieve_cpts_from_bro(self, params, **kwargs) -> SetParamsResult:
        """
        Retrieves available CPTs in the selected area from the BRO, using the bro package
        Saves intermediate result for showing of location + some metadata of the CPT object.
        """
        if not params.step_1.geo_polygon:
            raise UserError("No Polygon has been drawn yet, draw a polygon first.")

        envelope = self.get_envelope_from_polygon(params.step_1.geo_polygon)
        begin_date = datetime(2015, 1, 1).strftime("%Y-%m-%d")
        end_date = datetime.today().strftime("%Y-%m-%d")

        # TODO: Add logging for get_cpt_characteristics in V14
        try:
            cpt_characteristics = get_cpt_characteristics(begin_date, end_date, envelope)
        except ValueError as e:
            raise UserError(
                f"BRO REST API response: {e}"
            )
        except ReadTimeout as e:
            raise UserError(f"{e}")

        filtered_cpt_data = filter_available_cpts(params, cpt_characteristics)

        filtered_cpts = {
            "cpt_ids": filtered_cpt_data,
            "selected_polygon_points": [(p.lat, p.lon) for p in params.step_1.geo_polygon.points],
        }

        if not filtered_cpts["cpt_ids"]:
            raise UserError("No CPTs are available in the selected area. Please draw a larger polygon.")
        return SetParamsResult(params={"retrieved_cpts": json.dumps(filtered_cpts)})

    @staticmethod
    def get_envelope_from_polygon(geo_polygon: GeoPolygon) -> Envelope:
        """
        Creates an Envelope that can be used in the bro package.
        """
        latitudes, longitudes = map(list, zip(*[(p.lat, p.lon) for p in geo_polygon.points]))
        lower_corner = Point(min(latitudes), min(longitudes))
        upper_corner = Point(max(latitudes), max(longitudes))
        return Envelope(lower_corner, upper_corner)

    @staticmethod
    def get_nl_boundary_map_features() -> MapPolyline:
        """
        Gets the boundary of NL from a shapefile containing the provinces of NL.
        """
        # Read file with provinces information
        with open(Path(__file__).parent / "nl_provinces.json", "r", encoding="utf-8") as f:
            df = gpd.read_file(f).to_crs("WGS84")
            df["new_column"] = 0
            gdf_new = df.dissolve(by="new_column")

        points = []
        for coord in gdf_new["geometry"][0].exterior.coords:
            points.append(MapPoint(lon=coord[0], lat=coord[1]))
        return MapPolyline(*points)


def splitter(l: list, chunk_size: int):
    """
    Spliets a list in chunks, with set chunk size.
    """
    for i in range(0, len(l), chunk_size):
        yield l[i : i + chunk_size]


def visualize_cpts_with_classifications(
    all_cpt_models: List["CPT"],
) -> str:
    """Creates an interactive plot using plotly, showing the Robertson classification per CPT together with Qc / Rf values."""
    cols = len(all_cpt_models)
    fig = make_subplots(
        rows=1,
        cols=cols,
        shared_xaxes=True,
        shared_yaxes=True,
        horizontal_spacing=0.025,
        column_widths=cols * [3.5],
        subplot_titles=[cpt.name for cpt in all_cpt_models],
    )

    # Format axes and grids per subplot
    standard_grid_options = dict(showgrid=True, gridwidth=1, gridcolor="LightGrey")
    standard_line_options = dict(showline=True, linewidth=2, linecolor="LightGrey")

    unique_soil_names = set()
    cpts_using_penetration_length = []
    for col, cpt in enumerate(all_cpt_models, start=1):
        if cpt.warning_msg:
            cpts_using_penetration_length.append(cpt.name)

        # Add Qc plot
        fig.add_trace(
            go.Scatter(
                name="Cone Resistance",
                x=cpt.parsed_cpt.qc,
                y=[el * 1e-3 for el in cpt.parsed_cpt.elevation],
                mode="lines",
                line=dict(color="mediumblue", width=1),
                legendgroup="Cone Resistance",
                showlegend=bool(col == 1),
            ),
            row=1,
            col=col,
        )

        fig.update_xaxes(
            row=1,
            col=col,
            **standard_line_options,
            **standard_grid_options,
            range=[0, 40],
            tick0=0,
            dtick=5,
            title_text="qc [MPa] / Rf [%]",
            title_font=dict(color="black", size=10),
        )

        # Add Rf plot
        fig.add_trace(
            go.Scatter(
                name="Friction ratio",
                x=[rfval * 100 if rfval else rfval for rfval in cpt.parsed_cpt.Rf],
                y=[el * 1e-3 if el else el for el in cpt.parsed_cpt.elevation],
                mode="lines",
                visible=True,
                line=dict(color="red", width=1),
                legendgroup="Friction ratio",
                showlegend=bool(col == 1),
            ),
            row=1,
            col=col,
        )

        fig.update_yaxes(
            row=1,
            col=col,
            **standard_grid_options,
            title_text="Depth [m] w.r.t. NAP" if col == 1 else "",
            tick0=floor(all_cpt_models[0].parsed_cpt.elevation[-1] / 1e3) - 5,
            dtick=2,
        )

        # If no attribute is available
        if not hasattr(cpt, "soil_layout_original"):
            continue

        # Add bars for each soil type separately in order to be able to set legend labels
        unique_soil_types_in_cpt = {layer.soil.properties.ui_name for layer in [*cpt.soil_layout_original.layers]}

        for ui_name in unique_soil_types_in_cpt:
            soil_type_layers = [
                layer for layer in cpt.soil_layout_original.layers if layer.soil.properties.ui_name == ui_name
            ]

            fig.add_trace(
                go.Bar(
                    name=ui_name,
                    x=[20] * len(soil_type_layers),
                    y=[-layer.thickness * 1e-3 for layer in soil_type_layers],
                    width=40,
                    marker_color=[f"rgb{layer.soil.color.rgb}" for layer in soil_type_layers],
                    hovertext=[
                        f"Soil Type: {layer.soil.properties.ui_name}<br>"
                        f"Top of layer: {layer.top_of_layer * 1e-3:.2f}<br>"
                        f"Bottom of layer: {layer.bottom_of_layer * 1e-3:.2f}"
                        for layer in soil_type_layers
                    ],
                    hoverinfo="text",
                    opacity=0.5,
                    legendgroup=ui_name,
                    showlegend=bool(ui_name not in unique_soil_names),
                    base=[layer.top_of_layer * 1e-3 for layer in soil_type_layers],
                ),
                row=1,
                col=col,
            )

        unique_soil_names.update(unique_soil_types_in_cpt)

    # fig.add_hline(y=self.parsed_cpt.elevation[0] * 1e-3, line=dict(color='Black', width=1),
    #               row='all', col='all') # TODO Horizontal line for groundlevel: a bit ugly

    fig.update_layout(barmode="stack", template="plotly_white", legend=dict(x=1.05, y=0.5))

    fig.update_annotations(font_size=9)
    if cpts_using_penetration_length:
        fig.add_annotation(
            x=0.5,
            y=1.12,
            xref="paper",
            yref="paper",
            text=f"<b>The following CPTs use penetration length because depth information is missing: <br>"
            f"{' '.join(cpts_using_penetration_length)}. </b>",
            showarrow=False,
            font=dict(color="red"),
            borderwidth=1,
            bordercolor="black",
        )

    fig.update_yaxes(
        row=1,
        col=1,
        **standard_grid_options,
        title_text="Depth [m] w.r.t. NAP",
        tick0=floor(all_cpt_models[0].parsed_cpt.elevation[-1] / 1e3) - 5,
        dtick=2,
    )

    return fig.to_json()
