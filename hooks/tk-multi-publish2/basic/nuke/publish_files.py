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
import pprint
import nuke
import sgtk
from sgtk.platform import engine

HookBaseClass = sgtk.get_hook_baseclass()


class NukePublishFilesCustomPlugin(HookBaseClass):
    """
    Inherits from NukePublishFilesPlugin
    """
    def __init__(self, parent, **kwargs):
        """
        Construction
        """
        # call base init
        super(NukePublishFilesCustomPlugin, self).__init__(parent, **kwargs)

    def _sync_frame_range(self):
        """
        Checks whether frame range is in sync with shotgun.

        :return: True if yes false otherwise
        """
        # get the current engine
        engine = sgtk.platform.current_engine()
        # context from engine
        context = engine.context
        entity = context.entity

        sg_entity_type = context.entity["type"]
        sg_filters = [["id", "is", entity["id"]]]
        fields = ["cut_in", "cut_out"]

        # get the field information from shotgun based on Shot
        data = engine.shotgun.find_one(sg_entity_type, filters=sg_filters, fields=fields)
        # compare if the frame range set at root level is same as the shogun cut_in, cut_out
        root = nuke.Root()
        if root.firstFrame() != data["cut_in"] or root.lastFrame() != data["cut_out"]:
            self.logger.error("Frame range not synced with Shotgun.")
            return False
        return True

    def _non_sgtk_writes(self):
        """
        Checks for non SGTK write nodes present in the scene.

        :return: True if yes false otherwise
        """
        write_nodes = ""
        # get all write nodes
        write = nuke.allNodes('Write')
        if write:
            for item in range(len(write)):
                write_nodes += "\n" + write[item]['name'].value()
            self.logger.error("Non SGTK write nodes detected.",
                              extra={
                                  "action_show_more_info": {
                                      "label": "Show Info",
                                      "tooltip": "Show non sgtk write node(s)",
                                      "text": "Non SGTK write nodes:\n{}".format(write_nodes)
                                  }
                              }
                              )
            return False
        return True

    @staticmethod
    def _check_for_knob(node, knob):
        try:
            node[knob]
        except NameError:
            return False
        else:
            return True

    def _file_paths(self):
        """
        Checks if the files loaded are from valid paths i.e
        /dd/shows/<show_name> or /dd/library

        :return: True if paths are valid false otherwise
        """
        show = os.environ['DD_SHOW']
        valid_paths = ['/dd/shows/' + show, '/dd/library']
        paths = ""

        # For all the nodes present in the script, check for 'file' parameter.
        # If its populated, get the file path and check validity.
        for index, fileNode in enumerate(nuke.allNodes(), 0):
            # if the node has 'file' parameter, check if the file path is valid
            if self._check_for_knob(fileNode, 'file'):
                node_name = nuke.allNodes()[index]['name'].value()
                node_file_path = fileNode['file'].value()
                if node_file_path:
                    if valid_paths[0] in node_file_path or valid_paths[1] in node_file_path:
                        continue
                    else:
                        paths += "\n" + node_name + "  --->  " + node_file_path
        if paths:
            self.logger.error("Invalid paths! Try loading from shotgun.",
                              extra={
                                  "action_show_more_info": {
                                      "label": "Show Info",
                                      "tooltip": "Show invalid path(s)",
                                      "text": "Invalid paths!\n{}".format(paths)
                                  }
                              }
                              )
            return False
        return True

    def _bbsize(self):
        """
        Checks for oversized bounding box for shotgun write nodes.

        :return:True if all the write nodes have bounding boxes within limits
        """
        # Collecting sgtk write nodes
        node = nuke.allNodes('WriteTank')
        nodes = ""
        for index, item in enumerate(node, 0):
            bb = node[index].bbox()  # write node bbox
            bb_height = bb.h()  # bbox height
            bb_width = bb.w()  # bbox width

            node_h = node[index].height()  # write node height
            node_w = node[index].width()  # write node width
            tolerance_h = (bb_height - node_h) / node_h * 100
            tolerance_w = (bb_width - node_w) / node_w * 100

            # Check if the size if over 5%(tolerance limit)
            if tolerance_h > 5 or tolerance_w > 5:
                nodes += "\n" + node[index]['name'].value()
            if nodes:
                self.logger.error(
                    "Bounding Box resolution over the tolerance limit for write node(s).",
                    extra={
                        "action_show_more_info": {
                            "label": "Show Info",
                            "tooltip": "Show the write node(s)",
                            "text": "Bounding Box resolution over the tolerance limit for:\n{}".format(nodes)
                        }
                    }
                )
                return False
            return True

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
        status = True
        status = self._bbsize() and status
        status = self._file_paths() and status
        status = self._non_sgtk_writes() and status
        status = self._sync_frame_range() and status

        if not status:
            return status

        return super(NukePublishFilesCustomPlugin, self).validate(task_settings, item)

