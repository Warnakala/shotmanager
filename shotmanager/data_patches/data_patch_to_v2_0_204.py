# GPLv3 License
#
# Copyright (C) 2021 Ubisoft
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Data patch
"""

import bpy
from ..utils import utils

from shotmanager.config import config
from shotmanager.config import sm_logging

_logger = sm_logging.getLogger(__name__)

# 02/08/2022
# Patch to upgrade the shot manager data created with a shot manager version older than V.2.0.204

# v2_0_204: 2000204


def data_patch_to_v2_0_204():
    """Patch to introduce the layout settings"""
    _logger.debug_ext(f"Applying patch {'data_patch_to_v2_0_204'}...", col="PINK", tag="PATCH")

    for scene in bpy.data.scenes:
        props = None

        if getattr(scene, "UAS_shot_manager_props", None) is not None:
            props = scene.UAS_shot_manager_props

            _logger.debug_ext(
                f"   Data version: {props.dataVersion}, SM version: {bpy.context.window_manager.UAS_shot_manager_version}"
            )
            if props.dataVersion <= 0 or props.dataVersion < bpy.context.window_manager.UAS_shot_manager_version:
                prefs = config.getShotManagerPrefs()

                # apply patch and apply new data version
                #       print("       Applying data patch data_patch_to_v2_0_12 to scenes")

                props.createLayoutSettings()
                props.setCurrentLayout(prefs.layout_mode)

                # set right data version
                # props.dataVersion = bpy.context.window_manager.UAS_shot_manager_version
                props.dataVersion = bpy.context.window_manager.UAS_shot_manager_version
                print(
                    f"       Scene {scene.name}: Data upgraded to version V.{utils.convertVersionIntToStr(props.dataVersion)}"
                )
