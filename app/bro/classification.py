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
from copy import deepcopy
from math import ceil
from pathlib import Path
from typing import Dict
from typing import List
from typing import Union

from lxml import etree
from munch import munchify
from munch import unmunchify

from viktor import Color
from viktor import UserError
from viktor.errors import GEFClassificationError
from viktor.geo import GEFData as SDKGEFData
from viktor.geo import GEFParsingException
from viktor.geo import RobertsonMethod
from viktor.geo import Soil
from viktor.geo import SoilLayout

DEFAULT_MIN_LAYER_THICKNESS = 200
GEF_XML_MAPPING = {
    "Rf": "frictionRatio",
    "fs": "localFriction",
    "qc": "coneResistance",
    "elevation": "depth",
    "corrected_depth": "depth",
    "penetration_length": "penetrationLength",
}


def convert_xml_dict_to_cpt_dict(xml_dict) -> dict:
    xml_data = munchify(xml_dict).dispatchDocument.CPT_O
    measurement_data = {
        "Rf": [],
        "fs": [],
        "qc": [],
        "elevation": [],
        "corrected_depth": [],
    }
    elevation_offset = int(float(xml_data.deliveredVerticalPosition.offset) * 1000)
    mapping = {}
    for i, (tag, value) in enumerate(xml_data.conePenetrometerSurvey.parameters):
        for key, label in GEF_XML_MAPPING.items():
            if tag == label and value is True:
                try:
                    mapping[key] = i
                except KeyError as e:
                    raise UserError(f'Missing "{key}" in XML data') from e
    penetration_length_index = mapping.pop("penetration_length", None)

    token_separator = ","
    block_separator = ";"
    if xml_data.conePenetrometerSurvey.conePenetrationTest.cptResult.encoding.TextEncoding:
        x_ = xml_data
        token_separator = x_.conePenetrometerSurvey.conePenetrationTest.cptResult.encoding.TextEncoding.tokenSeparator
        block_separator = x_.conePenetrometerSurvey.conePenetrationTest.cptResult.encoding.TextEncoding.blockSeparator

    data_rows = [
        row.split(token_separator)
        for row in xml_data.conePenetrometerSurvey.conePenetrationTest.cptResult["values"].split(block_separator)[:-1]
    ]

    # For some reason, in some xml files the rows are scrambled, so we need to sort them by penetration length
    warning_msg = None

    try:
        # Force elevation to be penetration length if there is no data in the cpt for visualisation purposes.
        if "elevation" not in mapping:
            mapping["elevation"] = penetration_length_index
            mapping["corrected_depth"] = penetration_length_index
            warning_msg = "Penetration length used as elevation as data was missing"

        sorted_data = sorted(data_rows, key=lambda x: float(x[mapping["elevation"]]))

    except KeyError as e:
        # TODO: Add non-breaking user messages in V14
        raise UserError(f"Missing {e} in XML data") from e

    for data in sorted_data:
        for key, col_index in mapping.items():
            data_value = float(data[col_index])
            if data_value == float(-999999):
                measurement_data[key].append(None)
            else:
                if key == "elevation":
                    data_point = elevation_offset - int(data_value * 1000)
                elif key == "corrected_depth":
                    data_point = int(data_value * 1e3)
                elif key == "Rf":
                    data_point = data_value / 100
                else:
                    data_point = data_value
                measurement_data[key].append(data_point)

    if not measurement_data["Rf"]:  # If Rf is not provided in xml file, then calculate it
        measurement_data["Rf"] = [
            fs / qc if qc != 0 else None for qc, fs in zip(measurement_data["qc"], measurement_data["fs"])
        ]

    coneSurfaceQuotient = (
        float(xml_data.conePenetrometerSurvey.conePenetrometer.coneSurfaceQuotient)
        if "coneSurfaceQuotient" in xml_data.keys()
        else None
    )

    frictionSleeveSurfaceQuotient = (
        float(xml_data.conePenetrometerSurvey.conePenetrometer.coneSurfaceQuotient)
        if "frictionSleeveSurfaceQuotient" in xml_data.keys()
        else None
    )

    coneToFrictionSleeveDistance = (
        float(xml_data.conePenetrometerSurvey.conePenetrometer.coneToFrictionSleeveDistance)
        if "coneToFrictionSleeveDistance" in xml_data.keys()
        else None
    )

    coneSurfaceArea = (
        float(xml_data.conePenetrometerSurvey.conePenetrometer.coneSurfaceArea)
        if "coneSurfaceArea" in xml_data.keys()
        else None
    )

    frictionSleeveSurfaceArea = (
        float(xml_data.conePenetrometerSurvey.conePenetrometer.frictionSleeveSurfaceArea)
        if "frictionSleeveSurfaceArea" in xml_data.keys()
        else None
    )

    return {
        "headers": {
            "name": xml_data.broId,
            "gef_file_date": xml_data.researchReportDate.get("date"),
            "height_system": xml_data.deliveredVerticalPosition.verticalDatum,
            "fixed_horizontal_level": xml_data.deliveredVerticalPosition.localVerticalReferencePoint,
            "cone_type": xml_data.conePenetrometerSurvey.conePenetrometer.conePenetrometerType,
            "cone_tip_area": coneSurfaceArea,
            "friction_sleeve_area": frictionSleeveSurfaceArea,
            "surface_area_quotient_tip": coneSurfaceQuotient,
            "surface_area_quotient_friction_sleeve": frictionSleeveSurfaceQuotient,
            "distance_cone_to_centre_friction_sleeve": coneToFrictionSleeveDistance,
            "excavation_depth": xml_data.conePenetrometerSurvey.trajectory.predrilledDepth,
            "corrected_depth": float(xml_data.conePenetrometerSurvey.trajectory.finalDepth) * 1000,
            "x_y_coordinates": list(map(float, xml_data.deliveredLocation.location.pos.split(" "))),
            "ground_level_wrt_reference_m": float(xml_data.deliveredVerticalPosition.offset),
            "ground_level_wrt_reference": float(xml_data.deliveredVerticalPosition.offset) * 1000,
        },
        "measurement_data": measurement_data,
        "warning_msg": warning_msg,
    }


class CPTData(SDKGEFData):
    def __init__(self, cpt_dict: dict):
        super().__init__(gef_dict=cpt_dict)


class IMBROFile:
    def __init__(self, file_content: bytes):
        self.file_content = file_content

    @classmethod
    def from_file(cls, file_path: Union[str, Path]) -> "IMBROFile":
        """Instantiates the IMBROFile class from a file_path to an IMBRO xml file."""
        with Path(file_path).open("rb") as xml_file:
            file_content = xml_file.read()
        return cls(file_content=file_content)

    def parse(
        self,
        return_gef_data_obj: bool = False,
    ) -> Union[dict, CPTData]:
        """Parses the xml file and returns either a cpt dictionary or a CPTData object"""
        xml_dict = self._parse_xml_file(self.file_content)
        cpt_dict = convert_xml_dict_to_cpt_dict(xml_dict)
        if return_gef_data_obj:
            return CPTData(cpt_dict=cpt_dict)
        return cpt_dict

    def _parse_xml_file(self, file_content: bytes) -> dict:
        return self._parse_xml_to_dict_recursively(etree.fromstring(file_content))

    @classmethod
    def _parse_xml_to_dict_recursively(cls, node):
        """Builds the data object from the xml structure passed, therefore preserving the structure and the values"""
        if not node.getchildren():
            return node.text

        grand_children = {}
        for child in node.getchildren():
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "parameters":
                grand_children["parameters"] = [
                    (sub_child.tag.split("}")[-1], sub_child.text in {"ja", 1}) for sub_child in child
                ]
            else:
                grand_children[tag] = cls._parse_xml_to_dict_recursively(child)
        return grand_children


class CPT:
    def __init__(self, cpt_params=None, soils=None, **kwargs):
        if cpt_params:
            params = unmunchify(cpt_params)
            self.name = params["headers"]["name"]
            self.headers = munchify(params["headers"])
            self.params = params
            self.parsed_cpt = SDKGEFData(self.filter_nones_from_params_dict(params))
            self.warning_msg = params["warning_msg"]
            if "soil_layout_original" in params.keys():
                self.soil_layout_original = SoilLayout.from_dict(params["soil_layout_original"])
                self.bottom_of_soil_layout_user = params["bottom_of_soil_layout_user"]

            self._soils = soils

    @staticmethod
    def filter_nones_from_params_dict(raw_dict) -> dict:
        """Removes all rows which contain one or more None-values"""
        rows_to_be_removed = []
        for row_index, items in enumerate(zip(*raw_dict["measurement_data"].values())):
            if None in items:
                rows_to_be_removed.append(row_index)
        for row in reversed(rows_to_be_removed):
            for signal in raw_dict["measurement_data"].keys():
                del raw_dict["measurement_data"][signal][row]
        return raw_dict


def convert_soil_layout_from_mm_to_m(soil_layout: SoilLayout) -> SoilLayout:
    """Converts the units of the SoilLayout from mm to m."""
    serialization_dict = soil_layout.serialize()
    for layer in serialization_dict["layers"]:
        layer["top_of_layer"] = layer["top_of_layer"] / 1000
        layer["bottom_of_layer"] = layer["bottom_of_layer"] / 1000
    return SoilLayout.from_dict(serialization_dict)


def convert_soil_layout_from_m_to_mm(soil_layout: SoilLayout) -> SoilLayout:
    """Converts the units of the SoilLayout from m to mm."""
    serialization_dict = soil_layout.serialize()
    for layer in serialization_dict["layers"]:
        layer["top_of_layer"] = layer["top_of_layer"] * 1000
        layer["bottom_of_layer"] = layer["bottom_of_layer"] * 1000
    return SoilLayout.from_dict(serialization_dict)


def convert_soil_layout_to_input_table_field(soil_layout: SoilLayout) -> List[dict]:
    """Converts a SoilLayout to the parametrisation representation (Field = InputTable).

    :param soil_layout: SoilLayout
    :return: List containing dictionaries for the InputTable. Structure:
    [
    {'name': 'Zand grof', 'top_of_layer': -5},
    {'name': 'Zand grof', 'top_of_layer': -8},
    ...
    ]
    """
    table_input_soil_layers = [
        {"name": layer.soil.properties.ui_name, "top_of_layer": layer.top_of_layer} for layer in soil_layout.layers
    ]

    return table_input_soil_layers


def _update_color_string(classification_table: List[dict]) -> List[dict]:
    """Converts the RGB color strings in the table into a tuple (R, G, B)"""
    for row in classification_table:
        if not isinstance(row["color"], Color):
            row["color"] = convert_to_color(row["color"])
    return classification_table


def convert_to_color(rgb: Union[str, tuple]) -> Color:
    """Simple conversion function that always returns a Color object"""
    if isinstance(rgb, tuple):
        return Color(*rgb)
    return Color(*[int(element) for element in rgb.strip().split(",")])


def get_water_level(cpt_data_object) -> float:
    """Water level is assigned to the value parsed from GEF file if it exists, otherwise a default is assigned to 1m
    below the surface level"""
    if hasattr(cpt_data_object, "water_level"):
        water_level = cpt_data_object.water_level
    else:
        water_level = cpt_data_object.ground_level_wrt_reference / 1e3 - 1
    return water_level


class Classification:
    """This class handles all logic related to selecting the correct method and table for classification of CPTData.

    It also provides the correct soil mapping needs for the visualizations of the soil layers.
    """

    def __init__(self, robertson_table: List[Dict]):
        self._method = "robertson"
        self._table = unmunchify(robertson_table)

    @property
    def table(self) -> List[dict]:
        """Returns a cleaned up table that can be used for the Classification methods"""
        return _update_color_string(self._table)

    def method(self) -> RobertsonMethod:
        """Returns the appropriate _ClassificationMethod for the CPTData.classify() function"""
        if self._method == "robertson":
            return RobertsonMethod(self.table)
        raise UserError(f"The {self._method} method has not yet been implemented")

    @property
    def soil_mapping(self) -> dict:
        """Returns a mapping between the soil name visible in the UI and the Soil object used in the logic"""
        soil_mapping = {}
        for soil in self.table:
            ui_name = soil["ui_name"]
            properties = deepcopy(soil)
            if self._method == "robertson":
                del properties["color"]
            soil_mapping[ui_name] = Soil(soil["name"], convert_to_color(soil["color"]), properties=properties)
        return soil_mapping

    def classify_cpt_file(self, cpt_file: IMBROFile, saved_ground_water_level=None) -> dict:
        """Classify an uploaded CPT File based on the selected _ClassificationMethod"""

        try:
            # Parse the GEF file content
            cpt_data_object = cpt_file.parse(return_gef_data_obj=True)

            # Get the water level from user input, or calculate it from GEF
            if saved_ground_water_level is not None:
                ground_water_level = saved_ground_water_level
            else:
                ground_water_level = get_water_level(cpt_data_object)

            # Classify the CPTData object to get a SoilLayout
            soil_layout_obj = cpt_data_object.classify(method=self.method(), return_soil_layout_obj=True)

        except GEFParsingException as e:
            raise UserError(f"CPT Parsing: {str(e)}") from e
        except GEFClassificationError as e:
            raise UserError(f"CPT Classification: {str(e)}") from e

        # TODO: do we really want to apply a standard filtering whenever we classify a cpt file?
        soil_layout_filtered = soil_layout_obj.filter_layers_on_thickness(
            min_layer_thickness=DEFAULT_MIN_LAYER_THICKNESS,
            merge_adjacent_same_soil_layers=True,
        )
        soil_layout_filtered_in_m = convert_soil_layout_from_mm_to_m(soil_layout_filtered)

        # Serialize the parsed CPT File content and update it with the new soil layout
        cpt_dict = cpt_data_object.serialize()
        cpt_dict["soil_layout_original"] = soil_layout_obj.serialize()
        cpt_dict["bottom_of_soil_layout_user"] = ceil(soil_layout_obj.bottom) / 1e3
        cpt_dict["soil_layout"] = convert_soil_layout_to_input_table_field(soil_layout_filtered_in_m)
        cpt_dict["ground_water_level"] = ground_water_level
        cpt_dict["x_rd"] = cpt_dict["headers"]["x_y_coordinates"][0] if "x_y_coordinates" in cpt_dict["headers"] else 0
        cpt_dict["y_rd"] = cpt_dict["headers"]["x_y_coordinates"][1] if "x_y_coordinates" in cpt_dict["headers"] else 0
        cpt_dict["gef"] = {"cpt_data": {"min_layer_thickness": DEFAULT_MIN_LAYER_THICKNESS}}
        return cpt_dict
