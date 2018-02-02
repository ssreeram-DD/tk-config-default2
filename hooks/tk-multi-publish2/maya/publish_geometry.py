# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import maya.cmds as cmds
import maya.mel as mel
import sgtk
from sgtk import TankError
from sgtk.util.filesystem import ensure_folder_exists

HookBaseClass = sgtk.get_hook_baseclass()


DEFAULT_ITEM_TYPE_SETTINGS = {
    "maya.geometry": {
        "publish_type": "Alembic Cache",
        "publish_name_template": None,
        "publish_path_template": None
    }
}


class MayaPublishGeometryPlugin(HookBaseClass):
    """
    Inherits from PublishFilesPlugin
    """
    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Publish Maya Geometry"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        return """
        <p>This plugin publishes session geometry for the current session. Any
        session geometry will be exported to the path defined by this plugin's
        configured "Publish Template" setting. The plugin will fail to validate
        if the "AbcExport" plugin is not enabled or cannot be found.</p>
        """

    @property
    def settings_schema(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default_value": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts
        as part of its environment configuration.
        """
        schema = super(MayaPublishGeometryPlugin, self).settings_schema
        schema["Item Type Filters"]["default_value"] = ["maya.geometry"]
        schema["Item Type Settings"]["default_value"] = DEFAULT_ITEM_TYPE_SETTINGS
        return schema


    def accept(self, task_settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        # Run the parent acceptance method
        accept_data = super(MayaPublishGeometryPlugin, self).accept(task_settings, item)
        if not accept_data.get("accepted"):
            return accept_data

        # check that the AbcExport command is available!
        if not mel.eval("exists \"AbcExport\""):
            self.logger.debug(
                "Item not accepted because alembic export command 'AbcExport' "
                "is not available. Perhaps the plugin is not enabled?"
            )
            accept_data["accepted"] = False

        # return the accepted info
        return accept_data


    def validate(self, task_settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """
        # check that there is still geometry in the scene:
        if not cmds.ls(geometry=True, noIntermediate=True):
            error_msg = (
                "Validation failed because there is no geometry in the scene "
                "to be exported. You can uncheck this plugin or create "
                "geometry to export to avoid this error."
            )
            raise TankError(error_msg)

        return super(MayaPublishGeometryPlugin, self).validate(task_settings, item)


    def _copy_files(self, publish_path, item):
        """
        Overrides the inherited method for copying the work file to the publish location
        to instead export out the scene geometry to the publish_path location.

        :param publish_path: The output publish path string
        :param item: Item to process
        """
        publisher = self.parent

        # set the alembic args that make the most sense when working with Mari.
        # These flags will ensure the export of an Alembic file that contains
        # all visible geometry from the current scene together with UV's and
        # face sets for use in Mari.
        alembic_args = [
            # only renderable objects (visible and not templated)
            "-renderableOnly",
            # write shading group set assignments (Maya 2015+)
            "-writeFaceSets",
            # write uv's (only the current uv set gets written)
            "-uvWrite"
        ]

        # find the animated frame range to use:
        start_frame, end_frame = _find_scene_animation_range()
        if start_frame and end_frame:
            alembic_args.append("-fr %d %d" % (start_frame, end_frame))

        # Set the output path:
        # Note: The AbcExport command expects forward slashes!
        alembic_args.append("-file %s" % publish_path.replace("\\", "/"))

        # build the export command.  Note, use AbcExport -help in Maya for
        # more detailed Alembic export help
        abc_export_cmd = ("AbcExport -j \"%s\"" % " ".join(alembic_args))

        # ...and execute it:
        try:
            # ensure the publish folder exists:
            publish_folder = os.path.dirname(publish_path)
            ensure_folder_exists(publish_folder)

            publisher.log_debug("Executing command: %s" % abc_export_cmd)
            cmds.refresh(suspend=True)
            mel.eval(abc_export_cmd)
            cmds.refresh(suspend=False)
        except Exception as e:
            raise Exception("Failed to export Geometry: %s" % e)

        self.logger.debug(
            "Exported scene geometry to '%s'." % publish_path
        )

        return [publish_path]


def _find_scene_animation_range():
    """
    Find the animation range from the current scene.
    """
    # look for any animation in the scene:
    animation_curves = cmds.ls(typ="animCurve")

    # if there aren't any animation curves then just return
    # a single frame:
    if not animation_curves:
        return 1, 1

    # something in the scene is animated so return the
    # current timeline.  This could be extended if needed
    # to calculate the frame range of the animated curves.
    start = int(cmds.playbackOptions(q=True, min=True))
    end = int(cmds.playbackOptions(q=True, max=True))

    return start, end
