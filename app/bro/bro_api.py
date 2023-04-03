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
import asyncio
import warnings
from typing import Dict, List

import aiohttp
from bro import CPTCharacteristics
from shapely.geometry.point import Point as SPPoint
from shapely.geometry.polygon import Polygon as SPPolygon

from viktor.utils import memoize

CPT_OBJECT_URL = "https://publiek.broservices.nl/sr/cpt/v1/objects/"


def filter_available_cpts(params, cpts: List[CPTCharacteristics]) -> List[Dict]:
    """
    Filters available CPTs based on the given GeoPolygon in step 1.
    Necessary since the BRO only allows for square areas in case the type is Envelope.
    """
    polygon = SPPolygon([(p.lat, p.lon) for p in params.step_1.geo_polygon.points])

    filtered_cpts = []
    for cpt in cpts:
        _p = SPPoint(cpt.wgs84_coordinate.lat, cpt.wgs84_coordinate.lon)
        if _p.within(polygon):
            filtered_cpts.append(
                {
                    "bro_id": cpt.bro_id,
                    "lat": cpt.wgs84_coordinate.lat,
                    "lon": cpt.wgs84_coordinate.lon,
                }
            )
    return filtered_cpts


@memoize
def get_cpt_object_xml_async(bro_cpt_ids: List[str]):
    """
    Retrieves a list of cpt objects in bytes format asynchronously.
    """
    xml_strs = asyncio.run(_async_get_xml_bytes_of_bro_cpt(bro_cpt_ids))
    return xml_strs


async def _async_get_xml_bytes_of_bro_cpt(bro_cpt_ids: List[str]) -> List[str]:
    """
    Gathers all to be performed requests.
    """
    # Catch ResourceWarnings, raised by suspected non-closure of connections.
    # In reality they *are* closed, yet after a little while.
    # For more information, visit: https://github.com/aio-libs/aiohttp/pull/2045
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        async with aiohttp.ClientSession() as session:
            tasks = [async_get_cpt_object_xml(session, cpt_id) for cpt_id in bro_cpt_ids]
            xml_str_list = await asyncio.gather(*tasks, return_exceptions=False)
        await asyncio.sleep(0.1)
    return xml_str_list


async def async_get_cpt_object_xml(session, bro_cpt_id: str) -> str:
    """
    Performs the actual request, only adding registered CPTs.
    """
    headers_cpt = {
        "accept": "application/xml",
    }
    url = f"{CPT_OBJECT_URL}{bro_cpt_id}"

    async with session.get(url, headers=headers_cpt) as response:  # Set up the asynchronous request
        response.raise_for_status()
        content = await response.text()  # Wait for the response to arrive
        # Only retrieve registered CPT Objects.
        if "deregistrationTime" not in content:
            return content
