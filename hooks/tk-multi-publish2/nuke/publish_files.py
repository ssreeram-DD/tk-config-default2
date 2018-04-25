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
import nuke
import sgtk
import itertools
from dd.runtime import api
api.load("frangetools")
import frangetools

HookBaseClass = sgtk.get_hook_baseclass()


class NukePublishFilesDDValidationPlugin(HookBaseClass):
    """
    Inherits from NukePublishFilesPlugin
    """
    def _build_dict(self, seq, key):
        """
        Creating a dictionary based on a key.

        :param seq: list of dictionaries
        :param key: dictionary key from which to create the dictionary
        :return: dict with information for that particular key
        """
        return dict((d[key], dict(d, index=index)) for (index, d) in enumerate(seq))


    def _framerange_to_be_published(self, item):
        """
        Since users have the option to render only a subset of frames,
        adding validation to check if the full frame range is being published.

        :param item: Item to process
        :return: True if yes false otherwise
        """
        lss_path = item.properties['node']['cached_path'].value()
        lss_data = frangetools.getSequence(lss_path)

        # Since lss_data will be a list of dictionaries,
        # building a dictionary from key value for the ease of fetching data.
        info_by_path = self._build_dict(lss_data, key="path")
        missing_frames = info_by_path.get(lss_path)['missing_frames']
        root = nuke.Root()

        # If there are no missing frames, then checking if the first and last frames match with root first and last
        # Checking with root because _sync_frame_range() will ensure root is up to date with shotgun
        if missing_frames:
            self.logger.error("Incomplete renders! All the frames are not rendered.")
            return False
        else:
            first_rendered_frame = info_by_path.get(lss_path)['frame_range'][0]
            last_rendered_frame = info_by_path.get(lss_path)['frame_range'][1]
            if (first_rendered_frame != root.firstFrame()) or (last_rendered_frame != root.lastFrame()):
                self.logger.error("Incomplete renders! All the frames are not rendered.")
                return False
            return True


    def _sync_frame_range(self, item):
        """
        Checks whether frame range is in sync with shotgun.

        :param item: Item to process
        :return: True if yes false otherwise
        """
        context = item.context
        entity = context.entity

        sg_entity_type = entity["type"]
        sg_filters = [["id", "is", entity["id"]]]
        fields = ["sg_cut_in", "sg_cut_out"]

        # get the field information from shotgun based on Shot
        # sg_cut_in and sg_cut_out info will be on Shot entity, so skip in case this info is not present
        data = self.sgtk.shotgun.find_one(sg_entity_type, filters=sg_filters, fields=fields)
        if "sg_cut_in" not in data or "sg_cut_out" not in data:
            return True

        # compare if the frame range set at root level is same as the shotgun cut_in, cut_out
        root = nuke.Root()
        if root.firstFrame() != data["sg_cut_in"] or root.lastFrame() != data["sg_cut_out"]:
            self.logger.error("Frame range not synced with Shotgun.")
            return False
        return True


    def _non_sgtk_writes(self):
        """
        Checks for non SGTK write nodes present in the scene.

        :return: True if yes false otherwise
        """
        write_nodes = ""
        # get all write and write geo nodes
        write = nuke.allNodes('Write') + nuke.allNodes('WriteGeo')

        if write:
            for item in range(len(write)):
                write_nodes += "\n" + write[item].name()
            self.logger.error("Non SGTK write nodes detected here.",
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


    def _collect_nodes_in_graph(self, nodes):
        """
        For each WriteTank node, traverse the node graph and get the associated nodes.

        :param nodes: WriteTank node
        :return: list of associated nodes
        """
        dependency_list = list(itertools.chain(*(node.dependencies() for node in nodes)))
        if not dependency_list:
            return list(set(nodes))
        else:
            depend = self._collect_nodes_in_graph(dependency_list)
            for item in depend:
                nodes.append(item)
            return list(set(nodes))


    def _read_and_camera_file_paths(self, item):
        """
        Checks if the files loaded are published or from valid locations i.e
        /dd/shows/<show>/SHARED, dd/shows/<show>/<seq>/SHARED, dd/shows/<show>/<seq>/<shot>/SHARED
        or
        /dd/shows/<show>, /dd/library

        :param item: Item to process
        :return: True if paths are published or valid false otherwise
        """
        show = os.path.join(os.environ['DD_SHOWS_ROOT'], os.environ['DD_SHOW'])
        valid_paths = [show, os.path.join(os.environ['DD_ROOT'], 'library')]
        paths = ""

        publisher = self.parent
        unpublished = ""

        # Collect all the nodes associated with a write node
        # For all the read, readgeo and camera nodes present in the write node graph, check for 'file' knob.
        # If its populated, get the file path.
        related_nodes = self._collect_nodes_in_graph([item.properties['node']])
        node_type_list = ["Read", "ReadGeo2", "Camera2"]

        for index, fileNode in enumerate(related_nodes, 0):
            if (fileNode.Class() in node_type_list) and self._check_for_knob(fileNode, 'file'):
                node_name = related_nodes[index].name()
                node_file_path = fileNode['file'].value()
                sg_data = sgtk.util.find_publish(publisher.sgtk, [node_file_path])
                if node_file_path:
                    # Check if the file(s) loaded are published
                    # If they are not published, they should at least be from valid locations
                    if sg_data:
                        continue
                    elif any(path in node_file_path for path in valid_paths):
                        unpublished += "\n" + node_name + "  --->  " + node_file_path
                    else:
                        paths += "\n" + node_name + "  --->  " + node_file_path

        if unpublished:
            self.logger.warning(
                "Unpublished files found.",
                extra={
                    "action_show_more_info": {
                        "label": "Show Info",
                        "tooltip": "Show unpublished files",
                        "text": "Unpublished files.\n{}".format(unpublished)
                    }
                }
            )
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

    def _bbsize(self, item):
        """
        Checks for oversized bounding box for shotgun write nodes.

        :param item: Item to process
        :return:True if all the write nodes have bounding boxes within limits
        """
        node = item.properties['node']

        bb = node.bbox()  # write node bbox
        bb_height = bb.h()  # bbox height
        bb_width = bb.w()  # bbox width

        node_h = node.height()  # write node height
        node_w = node.width()  # write node width
        tolerance_h = (bb_height - node_h) / node_h * 100
        tolerance_w = (bb_width - node_w) / node_w * 100

        # Check if the size if over 5%(tolerance limit)
        if tolerance_h > 5 or tolerance_w > 5:
            self.logger.error(
                "Bounding Box resolution over the tolerance limit for write node.")
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
        # Segregating the checks, specifically for write nodes and for general nuke script
        if 'node' in item.properties.keys():
            status = self._bbsize(item) and status
            status = self._read_and_camera_file_paths(item) and status
            status = self._framerange_to_be_published(item) and status
        else:
            status = self._non_sgtk_writes() and status
            status = self._sync_frame_range(item) and status

        if not status:
            return status

        return super(NukePublishFilesDDValidationPlugin, self).validate(task_settings, item)

