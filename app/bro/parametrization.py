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

from viktor import UserError
from viktor.errors import InputViolation
from viktor.parametrization import (
    DownloadButton,
    GeoPolygonField,
    HiddenField,
    LineBreak,
    MapSelectInteraction,
    MultiSelectField,
    NumberField,
    OptionListElement,
    SetParamsButton,
    Step,
    Text,
    ToggleButton,
    ViktorParametrization,
)

ADDITIONAL_COLUMNS = [
    "corrected_depth",
    "fs",
    "u2",
    "inclination",
    "inclination_n_s",
    "inclination_e_w",
]

DEFAULT_ROBERTSON_TABLE = [
    {
        "name": "Robertson zone unknown",
        "ui_name": "Unknown material",
        "color": "255, 0, 0",
        "gamma_dry": 0,
        "gamma_wet": 0,
        "phi": 0,
    },
    {
        "name": "Robertson zone 1",
        "ui_name": "Soil, finely granular",
        "color": "200, 25, 0",
        "gamma_dry": 10,
        "gamma_wet": 10,
        "phi": 15,
    },
    {
        "name": "Robertson zone 2",
        "ui_name": "Peat, organic material",
        "color": "188, 104, 67",
        "gamma_dry": 12,
        "gamma_wet": 12,
        "phi": 15,
    },
    {
        "name": "Robertson zone 3",
        "ui_name": "Clay, weakly silty to silty",
        "color": "29, 118, 29",
        "gamma_dry": 15.5,
        "gamma_wet": 15.5,
        "phi": 17.5,
    },
    {
        "name": "Robertson zone 4",
        "ui_name": "Clay, silty / Loam",
        "color": "213, 252, 181",
        "gamma_dry": 18,
        "gamma_wet": 18,
        "phi": 22.5,
    },
    {
        "name": "Robertson zone 5",
        "ui_name": "Sand, silty to loam",
        "color": "213, 252, 155",
        "gamma_dry": 18,
        "gamma_wet": 20,
        "phi": 25,
    },
    {
        "name": "Robertson zone 6",
        "ui_name": "Sand, weakly silty to silty",
        "color": "255, 225, 178",
        "gamma_dry": 18,
        "gamma_wet": 20,
        "phi": 27,
    },
    {
        "name": "Robertson zone 7",
        "ui_name": "Sand - sand, gravelley",
        "color": "255, 183, 42",
        "gamma_dry": 17,
        "gamma_wet": 19,
        "phi": 32.5,
    },
    {
        "name": "Robertson zone 8",
        "ui_name": "Sand, solid - sand, clayey",
        "color": "200, 190, 200",
        "gamma_dry": 18,
        "gamma_wet": 20,
        "phi": 32.5,
    },
    {
        "name": "Robertson zone 9",
        "ui_name": "Soil, very stiff, fine-grained",
        "color": "186, 205, 224",
        "gamma_dry": 20,
        "gamma_wet": 22,
        "phi": 40,
    },
]

LINE_SCALE = 0.2


def _get_cpt_options(params, **kwargs):
    if params.retrieved_cpts:
        return [OptionListElement(cpt["bro_id"]) for cpt in json.loads(params.retrieved_cpts)["cpt_ids"]]
    return []


def validate_step_1(params, **kwargs):
    if not params.step_1.geo_polygon:
        violations = [
            InputViolation(
                "No Polygon has been drawn yet, draw a polygon first.",
                fields=["step_1.geo_polygon"],
            )
        ]
        raise UserError("No Polygon has been drawn yet.", input_violations=violations)

    if not params.retrieved_cpts:
        violations = [InputViolation("No CPTs have been retrieved yet.", fields=["step_1.retrieve_data"])]
        raise UserError("No CPTs have been retrieved yet.", input_violations=violations)

    if params.retrieved_cpts:
        if not json.loads(params.retrieved_cpts)["cpt_ids"]:
            violation = [
                InputViolation(
                    "No CPTs are available. Please draw a larger polygon.",
                    fields=["step_1.geo_polygon"],
                )
            ]
            raise UserError(
                "No CPTs are available. Please draw a larger polygon.",
                input_violations=violation,
            )

        violations = [
            InputViolation(
                "A new Polygon has been drawn, but the new CPTs have not been retrieved. "
                "Press 'Retrieve available CPTs' button first to continue.",
                fields=["step_1.retrieve_data"],
            )
        ]
        new_points = [[p.lat, p.lon] for p in params.step_1.geo_polygon.points]
        if json.loads(params.retrieved_cpts)["selected_polygon_points"] != new_points:
            raise UserError(
                "Press 'Retrieve available CPTs' button first to continue.",
                input_violations=violations,
            )


class Parametrization(ViktorParametrization):
    step_1 = Step("Location selection", views=["view_locations_step_1"], on_next=validate_step_1)

    step_1.introduction_text = Text(
        "# Welcome to the BRO app! \n"
        "With this app you will be ably to retrieve CPTs from the BRO by selecting an area on the map. "
        "These CPTs can subsequently be classified (Robertson method) and visualized or be downloaded as .XML file."
    )
    step_1.geo_polygon = GeoPolygonField(
        "## 1. Location definition  \n"
        "Draw a Polygon to define a bounding box by clicking the pencil.  \n"
        "You can choose to show the cpt names as labels with the 'Show labels' button.  \n"
        "Also, you can scale the label size for the 'Locations view'. "
    )
    step_1.show_labels = ToggleButton("Show labels", default=True, flex=50)
    step_1.label_size = NumberField("Label size", default=5, min=1, max=20, flex=50, variant="slider")
    step_1.txt = Text(
        "## 2. Retrieve CPTs from the BRO  \n"
        "Press the button below to retrieve available CPTs from the "
        "[BRO](https://www.broloket.nl/ondergrondgegevens).  \n"
        "**Always** press this button after you've changed your polygon."
    )
    step_1.retrieve_data = SetParamsButton("Retrieve available CPTs from the BRO", "retrieve_cpts_from_bro", flex=100)
    step_1.retrieved_cpts = HiddenField(" hidden", name="retrieved_cpts")

    step_2 = Step(
        "Downloads + Visualisation",
        views=["visualize_cpt_comparison", "view_locations_step_1"],
    )
    step_2.lb0 = LineBreak()
    step_2.signals_text = Text(
        "## 1. CPT classification comparison \n"
        "First select the CPTs you want to compare on the map by clicking the button below.  \n"
        "The classification is performed with the Robertson method."
    )
    step_2.select_cpts_on_map = SetParamsButton(
        "Select CPTs on the map",
        method="select_from_map",
        interaction=MapSelectInteraction("view_locations_step_1", min_select=1, max_select=10, selection=["points"]),
        flex=100,
    )

    step_2.lb1 = LineBreak()

    step_2.downloads_text = Text(
        "## 2. Visualisation and Downloads  \n"
        "Select and download XML files from the [BRO](https://www.broloket.nl/ondergrondgegevens).  \n"
        "The 'CPT comparison' view uses input from this field to visualize a CPT comparison that is classified "
        "with the Robertson method.  \n"
        "**Note**: Max. 10 CPTs can be shown in the 'CPT Comparison view'."
    )

    step_2.lb3 = LineBreak()
    step_2.signals_selected_cpts = MultiSelectField(
        "Select CPTs that you want to compare in the Graph comparison view",
        options=_get_cpt_options,
        flex=100,
    )
    step_2.download_selected_cpt_xml = DownloadButton(
        "Download selected CPTs from BRO (.XML)",
        method="download_selected_cpts_from_bro",
        longpoll=True,
        flex=50,
    )
    step_2.download_all_cpt_xml = DownloadButton(
        "Download all CPTs in area from BRO (.XML)",
        method="download_all_cpts_from_bro",
        longpoll=True,
        flex=50,
    )

    step_3 = Step("What's next?", views=["final_step"])
