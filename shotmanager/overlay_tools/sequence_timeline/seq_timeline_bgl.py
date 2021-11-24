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
Draw an interactive stack of shots in the Timeline editor

#TODO: clean code
"""

from collections import defaultdict
from statistics import mean

import gpu
import bgl, blf
import bpy
from gpu_extras.batch import batch_for_shader

from shotmanager.utils.utils import clamp, gamma_color, darken_color, remap
from shotmanager.utils.utils_ogl import get_region_at_xy, Square

# import mathutils

from shotmanager.config import sm_logging

_logger = sm_logging.getLogger(__name__)


class BL_UI_Cursor:
    def __init__(self, move_callback=None):
        self.context = None

        self.range_min = 0
        self.range_max = 100
        self._value = 0

        self.posx = 0
        self.posy = 36

        self.sizex = 15
        self.sizey = 8

        # Is used for drawing the frame number and for cursor interaction
        # origine of the referentiel is bottom left
        self.bboxbg = Square(self.posx + self.sizex + 1, self.posy - 1, self.sizex + 1, self.sizey + 1)
        self.bbox = Square(self.posx + self.sizex, self.posy, self.sizex, self.sizey)
        self.caret = Square(self.posx, self.posy - self.sizey, 3, 4)

        self.hightlighted = False
        self.edit_time = 0

        # normal play mode
        self.color = (0.1, 0.5, 0.2, 1)
        self.hightlighted_color = (0.2, 0.7, 0.3, 1)
        self.darken_color = (0.2, 0.2, 0.2, 1)

        self.disabled_color = (0.25, 0.25, 0.25, 1)

        self._p_mouse_x = 0
        self._mouse_down = False
        self._dragable = False
        self._move_callback = move_callback
        self.__inrect = False
        self.__area = None
        self.__region = None

        self.time_is_invalid = False

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = clamp(value, self.range_min, self.range_max)

    def init(self, context, cursor_forShotPlayMode=False):
        self.context = context
        self.__area = context.area

        if cursor_forShotPlayMode:
            self.color = (0.2, 0.2, 1.0, 1)
            self.hightlighted_color = (0.3, 0.3, 1.0, 1)
            self.darken_color = (0.1, 0.1, 0.3, 1)

    def draw(self):
        props = self.context.scene.UAS_shot_manager_props
        fix_offset_x = 1
        self.bbox.color = self.color
        self.bboxbg.color = self.darken_color
        self.caret.color = self.color
        if self.hightlighted:
            self.bbox.color = self.hightlighted_color
            self.caret.color = self.hightlighted_color

        box_to_draw_bg = self.bboxbg.copy()
        box_to_draw_bg.x = self.posx + 1 + fix_offset_x
        box_to_draw = self.bbox.copy()
        box_to_draw.x = self.posx + fix_offset_x
        caret_to_draw = self.caret.copy()
        caret_to_draw.x = self.posx + fix_offset_x
        edit_start_frame = props.editStartFrame
        if self.context.window_manager.UAS_shot_manager_shots_play_mode:
            scene_edit_time = props.getEditCurrentTime(ignoreDisabled=not props.seqTimeline_displayDisabledShots)
        else:
            scene_edit_time = props.getEditCurrentTimeForSelectedShot(
                ignoreDisabled=not props.seqTimeline_displayDisabledShots
            )

        self.time_is_invalid = False
        if not self._dragable:

            if -1 == scene_edit_time:
                current_frame = bpy.context.scene.frame_current
                prevShotInd = props.getFirstShotIndexBeforeFrame(
                    current_frame, ignoreDisabled=not props.seqTimeline_displayDisabledShots
                )
                # _logger.debug(f"scene_edit_time is -1. prevShotInd: {prevShotInd}")
                if -1 != prevShotInd:
                    shotList = props.get_shots()
                    scene_edit_time = props.getEditTime(
                        shotList[prevShotInd],
                        shotList[prevShotInd].end,
                        ignoreDisabled=not props.seqTimeline_displayDisabledShots,
                    )
                    # we add 1 frame here to place the cursor right after the end of the shot, not on the latest frame
                    scene_edit_time += 1
                #    _logger.debug(f"scene_edit_time shot not found: {scene_edit_time}")
                else:
                    scene_edit_time = edit_start_frame

                self.time_is_invalid = True
            else:
                scene_edit_time = max(edit_start_frame, scene_edit_time)
                self.time_is_invalid = False

            val = remap(
                scene_edit_time,
                edit_start_frame,
                props.getEditDuration(ignoreDisabled=not props.seqTimeline_displayDisabledShots) + edit_start_frame,
                0,
                self.context.area.width,
            )
            self.value = remap(val, 0, self.context.area.width, self.range_min, self.range_max)
        else:
            val = remap(self.value, self.range_min, self.range_max, 0, self.context.area.width)

        box_to_draw_bg.x = val + 1 + fix_offset_x
        box_to_draw_bg.x = max(box_to_draw_bg.sx, box_to_draw_bg.x)
        box_to_draw_bg.x = min(box_to_draw_bg.x, self.context.area.width - 1 - box_to_draw_bg.sx)

        caret_to_draw.x = val + fix_offset_x

        box_to_draw.x = val + fix_offset_x
        box_to_draw.x = max(box_to_draw.sx, box_to_draw.x)
        box_to_draw.x = min(box_to_draw.x, self.context.area.width - 1 - box_to_draw.sx)

        # shadow underneath
        box_to_draw_bg.draw()

        # micro rect bellow the cursor
        caret_to_draw.draw()

        # cursor
        if self.time_is_invalid:
            box_to_draw.color = self.disabled_color
        box_to_draw.draw()

        # edit time value displayed on cursor
        if self.context.window_manager.UAS_shot_manager_shots_play_mode:
            edit_time_without_disabled = props.getEditCurrentTime(ignoreDisabled=True)

        frameStr = str(max(edit_time_without_disabled, edit_start_frame)) if not self.time_is_invalid else "."
        blf.color(0, 0.9, 0.9, 0.9, 1)
        blf.size(0, 12, 72)
        font_width, font_height = blf.dimensions(0, frameStr)
        blf.position(0, box_to_draw.x - 0.5 * font_width, box_to_draw.y - 0.5 * font_height, 0)
        blf.draw(0, frameStr)

    #   print("\nscene_edit_time 02: ", scene_edit_time)

    def is_in_rect(self, x, y):
        if self.__region is not None:
            x -= self.__region.x
            y -= self.__region.y
            self.bbox.x = remap(self.value, self.range_min, self.range_max, 0, self.__area.width)
            self.bbox.x = clamp(self.bbox.x, self.bbox.sx, self.__area.width - self.bbox.sx)
            bound_lo, bound_hi = self.bbox.bbox()
            if bound_lo[0] <= x < bound_hi[0] and bound_lo[1] <= y < bound_hi[1]:
                return True

        return False

    def handle_event(self, event):
        x = event.mouse_x
        y = event.mouse_y

        tmp_region, tmp_area = get_region_at_xy(self.context, x, y)
        if tmp_area is not None:
            self.__region, self.__area = tmp_region, tmp_area
        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                self._mouse_down = True
                return self.mouse_down(x, y)
            else:
                self._mouse_down = False
                self.mouse_up(x, y)

        elif event.type == "MOUSEMOVE":
            self.mouse_move(x, y)
            inrect = self.is_in_rect(x, y)

            # we enter the rect
            if not self.__inrect and inrect:
                self.__inrect = True
                self.mouse_enter(event, x, y)

            # we are leaving the rect
            elif self.__inrect and not inrect:
                self.__inrect = False
                self.mouse_exit(event, x, y)

            return False

        return False

    def mouse_down(self, x, y):
        if self.is_in_rect(x, y):
            self._p_mouse_x = x
            self._dragable = True
            return True

        return False

    def mouse_up(self, x, y):
        self._dragable = False
        self.hightlighted = False

    def mouse_enter(self, event, x, y):
        self.hightlighted = True

    def mouse_exit(self, event, x, y):
        self.hightlighted = False

    def mouse_move(self, x, y):
        if self._dragable and self.__area is not None:
            # self.posx += x - self._p_mouse_x
            self.value += (x - self._p_mouse_x) * (self.range_max - self.range_min) / self.__area.width
            self._p_mouse_x = x
            if self._move_callback is not None:
                self._move_callback()


class BL_UI_Shot:
    def __init__(self, x, y, width, height, label, bypass_state):
        self.x = x
        self.y = y
        self.x_screen = x
        self.y_screen = y
        self.width = width
        self.height = height
        self.label = label
        self.bypass_state = bypass_state
        self._bg_color = (0.8, 0.3, 0.3, 1.0)
        self._label_color = (0.05, 0.05, 0.05, 1)
        self.context = None
        self.__inrect = False
        self._mouse_down = False

    def set_location(self, x, y):
        self.x = x
        self.y = y
        self.x_screen = x
        self.y_screen = y

    @property
    def bg_color(self):
        return self._bg_color

    @bg_color.setter
    def bg_color(self, value):
        self._bg_color = value
        if mean(self._bg_color[:-1]) < 0.4:
            self._label_color = (0.9, 0.9, 0.9, 1)

        if self.bypass_state:
            self._bg_color = (0.2, 0.2, 0.2, 1)

    def init(self, context):
        self.context = context

    def draw(self):
        area_height = self.get_area_height()

        self.x_screen = self.x
        self.y_screen = area_height - self.y

        indices = ((0, 1, 2), (0, 2, 3))

        y_screen_flip = area_height - self.y_screen
        # bottom left, top left, top right, bottom right
        vertices = (
            (self.x_screen, y_screen_flip),
            (self.x_screen, y_screen_flip - self.height),
            (self.x_screen + self.width, y_screen_flip - self.height),
            (self.x_screen + self.width, y_screen_flip),
        )

        shader = gpu.shader.from_builtin("2D_UNIFORM_COLOR")
        batch_panel = batch_for_shader(shader, "TRIS", {"pos": vertices}, indices=indices)

        shader.bind()
        shader.uniform_float("color", self._bg_color)
        bgl.glEnable(bgl.GL_BLEND)
        batch_panel.draw(shader)
        bgl.glDisable(bgl.GL_BLEND)

        blf.position(0, self.x_screen + 2, y_screen_flip - self.height * 0.5, 0)
        blf.color(0, *self._label_color)
        blf.shadow(0, 3, 0.1, 0.1, 0.1, 1)
        blf.size(0, 14, 72)
        blf.draw(0, self.label)

    def handle_event(self, event):
        x = event.mouse_region_x
        y = event.mouse_region_y

        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                self._mouse_down = True
                return self.mouse_down(x, y)
            else:
                self._mouse_down = False
                self.mouse_up(x, y)

        elif event.type == "MOUSEMOVE":
            self.mouse_move(x, y)

            inrect = self.is_in_rect(x, y)

            # we enter the rect
            if not self.__inrect and inrect:
                self.__inrect = True
                self.mouse_enter(event, x, y)

            # we are leaving the rect
            elif self.__inrect and not inrect:
                self.__inrect = False
                self.mouse_exit(event, x, y)

            return False

        return False

    def get_area_height(self):
        return self.context.area.height

    def is_in_rect(self, x, y):
        area_height = self.get_area_height()

        widget_y = area_height - self.y_screen
        if (self.x_screen <= x <= (self.x_screen + self.width)) and (widget_y >= y >= (widget_y - self.height)):
            return True

        return False

    def mouse_down(self, x, y):
        return self.is_in_rect(x, y)

    def mouse_up(self, x, y):
        pass

    def mouse_enter(self, event, x, y):
        pass

    def mouse_exit(self, event, x, y):
        pass

    def mouse_move(self, x, y):
        pass


class BL_UI_Timeline:
    def __init__(self, x, y, width, height, target_area=None):
        self.x = x
        self.y = y
        self.x_screen = x
        self.y_screen = y
        self.y_offset = 0
        self.width = width
        self.height = height
        self._mouse_y = 0
        self._bg_color = (0.1, 0.1, 0.1, 0.85)
        self.context = None
        self.target_area = target_area
        self.__inrect = False
        self._mouse_down = False

        self.ui_shots = list()
        self.frame_cursor = BL_UI_Cursor(self.frame_cursor_moved)
        self.frame_cursor_forShotPlayMode = BL_UI_Cursor(self.frame_cursor_moved)

    def set_location(self, x, y):
        self.x = x
        self.y = y
        self.x_screen = x
        self.y_screen = y

    @property
    def bg_color(self):
        return self._bg_color

    @bg_color.setter
    def bg_color(self, value):
        self._bg_color = value

    def init(self, context):
        self.context = context
        self.frame_cursor.init(context)
        self.frame_cursor_forShotPlayMode.init(context, cursor_forShotPlayMode=True)

    def draw_caret(self, x, color):
        caret_width = 3
        area_height = self.get_area_height()

        y = self.height + self.y_offset
        x_screen = x

        indices = ((0, 1, 2), (0, 2, 3))

        y_screen_flip = area_height - self.y_screen
        # bottom left, top left, top right, bottom right
        vertices = (
            (x_screen, y_screen_flip),
            (x_screen, y_screen_flip - self.height),
            (x_screen + caret_width, y_screen_flip - self.height),
            (x_screen + caret_width, y_screen_flip),
        )

        shader = gpu.shader.from_builtin("2D_UNIFORM_COLOR")
        batch_panel = batch_for_shader(shader, "TRIS", {"pos": vertices}, indices=indices)

        shader.bind()
        # shader.uniform_float ( "color", ( 1., .1, .1, 1 ) )
        shader.uniform_float("color", color)
        bgl.glEnable(bgl.GL_BLEND)
        batch_panel.draw(shader)
        bgl.glDisable(bgl.GL_BLEND)

    def draw_frame_caret(self, x, frame_width, color):
        caret_width = frame_width
        caret_height = self.height * 0.35
        area_height = self.get_area_height()

        y = caret_height + self.y_offset
        x_screen = x

        indices = ((0, 1, 2), (0, 2, 3))

        y_screen_flip = area_height - self.y_screen
        # bottom left, top left, top right, bottom right
        vertices = (
            (x_screen, y_screen_flip - self.height),
            (x_screen, y_screen_flip - self.height + caret_height),
            (x_screen + caret_width, y_screen_flip - self.height + caret_height),
            (x_screen + caret_width, y_screen_flip - self.height),
        )

        shader = gpu.shader.from_builtin("2D_UNIFORM_COLOR")
        batch_panel = batch_for_shader(shader, "TRIS", {"pos": vertices}, indices=indices)

        shader.bind()
        # shader.uniform_float("color", (1.0, 0.1, 0.1, 1))
        shader.uniform_float("color", color)
        bgl.glEnable(bgl.GL_BLEND)
        batch_panel.draw(shader)
        bgl.glDisable(bgl.GL_BLEND)

    def draw_shots(self):
        total_range = 0
        props = self.context.scene.UAS_shot_manager_props
        shots = props.getShotsList(ignoreDisabled=not props.seqTimeline_displayDisabledShots)
        currentShotIndex = props.getCurrentShotIndex(ignoreDisabled=not props.seqTimeline_displayDisabledShots)

        self.ui_shots.clear()
        total_range += sum([s.end + 1 - s.start for s in shots])
        offset_x = 0
        for i, shot in enumerate(shots):
            size_x = int(self.width * float(shot.end + 1 - shot.start) / total_range)
            s = BL_UI_Shot(offset_x, self.y, size_x, self.height, shot.name, not shot.enabled)
            self.ui_shots.append(s)
            s.init(self.context)
            s.bg_color = tuple(gamma_color(shot.color))

            s.draw()

            caret_pos = offset_x + (self.context.scene.frame_current - shot.start) * size_x / float(
                shot.end + 1 - shot.start
            )
            frame_width = size_x / float(shot.end + 1 - shot.start)

            if self.context.window_manager.UAS_shot_manager_shots_play_mode:
                if currentShotIndex == i:
                    caret_color = (1.0, 0.1, 0.1, 1)
                    self.draw_frame_caret(caret_pos, frame_width, darken_color(caret_color))
                    self.draw_caret(caret_pos, caret_color)
            else:
                if shot.start <= self.context.scene.frame_current and self.context.scene.frame_current <= shot.end:
                    caret_color = (0.1, 1.0, 0.1, 1)
                    self.draw_frame_caret(caret_pos, frame_width, darken_color(caret_color))
                    self.draw_caret(caret_pos, caret_color)

            offset_x += int(self.width * float(shot.end + 1 - shot.start) / total_range)

    def draw(self):
        if self.target_area is not None and self.context.area != self.target_area:
            return

        self.width = self.context.area.width
        area_height = self.get_area_height()

        self.y = self.height + self.y_offset
        self.x_screen = self.x
        self.y_screen = area_height - self.y

        indices = ((0, 1, 2), (0, 2, 3))

        y_screen_flip = area_height - self.y_screen
        # bottom left, top left, top right, bottom right
        vertices = (
            (self.x_screen, y_screen_flip),
            (self.x_screen, y_screen_flip - self.height),
            (self.x_screen + self.width, y_screen_flip - self.height),
            (self.x_screen + self.width, y_screen_flip),
        )

        shader = gpu.shader.from_builtin("2D_UNIFORM_COLOR")
        batch_panel = batch_for_shader(shader, "TRIS", {"pos": vertices}, indices=indices)

        shader.bind()
        shader.uniform_float("color", self._bg_color)
        bgl.glEnable(bgl.GL_BLEND)
        batch_panel.draw(shader)
        bgl.glDisable(bgl.GL_BLEND)

        self.draw_shots()
        if self.context.window_manager.UAS_shot_manager_shots_play_mode:
            self.frame_cursor_forShotPlayMode.draw()
        else:
            self.frame_cursor.draw()

    def handle_event(self, event):

        prefs = bpy.context.preferences.addons["shotmanager"].preferences
        if hasattr(bpy.context.space_data, "overlay"):
            if prefs.seqTimeline_not_disabled_with_overlays and not bpy.context.space_data.overlay.show_overlays:
                return False

        if self.target_area is not None and self.context.area != self.target_area:
            return False

        if self.context.window_manager.UAS_shot_manager_shots_play_mode:
            if self.frame_cursor_forShotPlayMode.handle_event(event):
                return True
        else:
            if self.frame_cursor.handle_event(event):
                return True

        x = event.mouse_region_x
        y = event.mouse_region_y

        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                self._mouse_down = True
                return self.mouse_down(x, y)
            else:
                self._mouse_down = False
                self.mouse_up(x, y)

        elif event.type == "MOUSEMOVE":
            self.mouse_move(x, y)

            inrect = self.is_in_rect(x, y)

            # we enter the rect
            if not self.__inrect and inrect:
                self.__inrect = True
                self.mouse_enter(event, x, y)
                self.bg_color = (0.5, 0.5, 0.5, 0.85)

            # we are leaving the rect
            elif self.__inrect and not inrect:
                self.__inrect = False
                self.mouse_exit(event, x, y)
                self.bg_color = (0.1, 0.1, 0.1, 0.85)

            return False

        return False

    def get_area_height(self):
        return self.context.area.height

    def is_in_rect(self, x, y):
        area_height = self.get_area_height()

        widget_y = area_height - self.y_screen
        if (self.x_screen <= x <= (self.x_screen + self.width)) and (widget_y >= y >= (widget_y - self.height)):
            return True

        return False

    def frame_cursor_moved(self):
        props = self.context.scene.UAS_shot_manager_props
        # shots = props.getShotsList(ignoreDisabled=not props.seqTimeline_displayDisabledShots)
        shots = props.get_shots()

        # get the right frame_cursor
        if self.context.window_manager.UAS_shot_manager_shots_play_mode:
            current_frame_cursor = self.frame_cursor_forShotPlayMode
        else:
            current_frame_cursor = self.frame_cursor

        new_edit_frame = round(
            remap(
                current_frame_cursor.value,
                current_frame_cursor.range_min,
                current_frame_cursor.range_max,
                props.editStartFrame,
                props.editStartFrame
                + props.getEditDuration(ignoreDisabled=not props.seqTimeline_displayDisabledShots)
                - 1,
            )
        )
        sequence_current_frame = props.editStartFrame
        for i, shot in enumerate(shots):
            if shot.enabled or props.seqTimeline_displayDisabledShots:
                if sequence_current_frame <= new_edit_frame < sequence_current_frame + shot.getDuration():
                    props.setCurrentShotByIndex(i)
                    props.setSelectedShotByIndex(i)
                    self.context.scene.frame_current = shot.start + new_edit_frame - sequence_current_frame
                    break
                sequence_current_frame += shot.getDuration()

    def mouse_down(self, x, y):
        return False  # self.is_in_rect ( x, y )

    def mouse_up(self, x, y):
        pass

    def mouse_enter(self, event, x, y):
        pass

    def mouse_exit(self, event, x, y):
        pass

    def mouse_move(self, x, y):
        pass

