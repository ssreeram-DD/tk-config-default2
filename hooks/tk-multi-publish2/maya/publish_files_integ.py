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

HookBaseClass = sgtk.get_hook_baseclass()

_group_nodes = ['WORLDSCALE',
                'SET_TO_WORLD',
                'TRACK_GEO']

_camera_name = 'CAM'

_default_cameras = ['persp',
                    'top',
                    'front',
                    'side']


class MayaPublishFilesDDIntegValidationPlugin(HookBaseClass):
    """
    Inherits from MayaPublishPlugin
    """

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        desc = super(MayaPublishFilesDDIntegValidationPlugin, self).description

        return desc + "<br><br>" + """
        Validation checks before a file is published.
        """

    def _extra_nodes(self, children):
        """
        Check for nodes, apart from groups and camera lying outside of TRACK_GEO node
        :param children:
        :return:
        """
        extras = list(set(cmds.ls(tr=True, dag=True)) - set(_group_nodes) - set(cmds.listCameras()) - set(children))

        if extras:
            node_names = ""
            for node in extras:
                node_names += "\n" + node
            self.logger.error("Nodes present outside TRACK_GEO.",
                              extra={
                                  "action_show_more_info": {
                                      "label": "Show Info",
                                      "tooltip": "Show the extra nodes",
                                      "text": "Nodes outside TRACK_GEO:\n{}".format(node_names)
                                  }
                              }
                              )
            return False
        return True

    def _locked_channels(self, nodes):
        """Check for locked channels for all nodes under the group TRACK_GEO.
            :param:
                nodes: list of nodes under TRACK_GEO
        """
        locked = ""
        for node in nodes:
            # For each node, list out attributes which are locked
            lock_per_node = cmds.listAttr(node, l=True)
            if lock_per_node:
                locked += "\n" + node + "  --->  " + ", ".join(lock_per_node)
        # If there are locked channels, error message with node name and locked attribute name(s).
        if locked:
            self.logger.error("Locked channels detected.",
                              extra={
                                  "action_show_more_info": {
                                      "label": "Show Info",
                                      "tooltip": "Show the node and locked channels",
                                      "text": "Locked channels:\n{}".format(locked)
                                  }
                              }
                              )
            return False
        return self._extra_nodes(nodes)

    def _track_geo_child_naming(self, track_geo):
        """Checks if the name of nodes under TRACK_GEO are prefixed with 'integ_'.
            :param:
                track_geo: nodes under TRACK_GEO
        """
        # Nodes under TRACK_GEO group
        children = cmds.listRelatives(track_geo, c=True)
        error_names = ""
        # if there are nodes under TRACK_GEO, check for one without prefix "integ_"
        if children:
            for child in children:
                # If the name doesn't start with integ_ add node name to errorNames
                if child[:6] != "integ_":
                    error_names += "\n" + child
        if error_names:
            self.logger.error("Incorrect Naming! Node name should start with integ_.",
                              extra={
                                  "action_show_more_info": {
                                      "label": "Show Info",
                                      "tooltip": "Show the node with incorrect naming",
                                      "text": "Nodes with incorrect naming:\n{}".format(error_names)
                                  }
                              }
                              )
            return False

        if children:
            # if there are nodes under TRACK_GEO, check for locked channels
            return self._locked_channels(children)
        else:
            return True

    def _check_hierarchy(self, group_nodes):
        """Checks the hierarchy of group nodes in the scene.
            :param:
                group_nodes: the list of nodes in the scene
        """
        for name in range(len(group_nodes) - 1):
            # Listing children of group nodes
            children = cmds.listRelatives(group_nodes[name], c=True)
            # group_nodes is arranged in hierarchial order i.e. the next node should be the child of previous
            if children and (group_nodes[name + 1] in children):
                if name == 'SET_TO_WORLD' and 'CAM' in children:
                    continue
            else:
                hierarchy = "WORLDSCALE\n|__SET_TO_WORLD\n" + "    " + "|__TRACK_GEO\n" + "    " + "|__CAM"
                self.logger.error("Incorrect hierarchy.",
                                  extra={
                                      "action_show_more_info": {
                                          "label": "Show Info",
                                          "tooltip": "Show the required hierarchy",
                                          "text": "Required hierarchy:\n\n{}".format(hierarchy)
                                      }
                                  }
                                  )
                return False
        return self._track_geo_child_naming(group_nodes[-1])

    def _connected_image_plane(self, camera):
        camshape = cmds.listRelatives(camera, s=True, c=True)[0]
        connections = cmds.listConnections(camshape + '.imagePlane', source=True, type='imagePlane')
        if not connections:
            self.logger.error("Image plane not attached to CAM.")
            return False
        return True

    def _camera_naming(self, group_nodes):
        """Checks the naming of the camera.
            :param:
                group_nodes: The list of nodes that should be in the scene. This will be
                used to check node hierarchy once camera naming is validated.
        """
        # Look for all the cameras present in the scene
        all_cameras = cmds.listCameras()
        # Remove the default_cameras from the list
        main_cam = list(set(all_cameras) - set(_default_cameras))
        if main_cam:
            if len(main_cam) > 1:
                # Checking if more than one CAM present
                self.logger.error("More the one camera detected. Only CAM should be present.")
                return False
            elif main_cam[0] != _camera_name:
                # Validating camera name
                self.logger.error("Incorrect camera name! Should be CAM.")
                return False
        else:
            self.logger.error("Camera (CAM) not present in the scene.")
            return False
        return self._connected_image_plane(main_cam[0])

    def _node_naming(self, group_nodes, groups):
        """Checking if the established group node names have not been tampered with.
            :param:
                group_nodes: group nodes to be present in the scene
                groups: group nodes that are actually present
        """
        # Check for extra group nodes apart from the ones in group_nodes
        names = ""
        extras = list(set(groups) - set(group_nodes))
        # check for any group nodes apart from the once mentioned
        if extras:
            for item in extras:
                names += "\n" + item
            self.logger.error("Incorrect naming or extra group nodes present in the scene.",
                              extra={
                                  "action_show_more_info": {
                                      "label": "Show Info",
                                      "tooltip": "Show the conflicting group nodes",
                                      "text": "Please check the group nodes:\n{}".format(names) +
                                              "\n\nOnly following group nodes should be present:\nWORLDSCALE \nSET_TO_WORLD \nTRACK_GEO"
                                  }
                              }
                              )
            return False
        # check if any of the required group nodes are missing
        elif not set(group_nodes).issubset(set(groups)):
            self.logger.error("Please ensure all the group nodes are present.",
                              extra={
                                  "action_show_more_info": {
                                      "label": "Show Info",
                                      "tooltip": "Group nodes",
                                      "text": "Following group nodes should be present:\nWORLDSCALE \nSET_TO_WORLD \nTRACK_GEO"
                                  }
                              }
                              )
            return False
        return self._check_hierarchy(group_nodes)

    @staticmethod
    def _is_group(node=None):
        """Check for all the group nodes present in the scene.
            :param:
                node: all the nodes in the scene
        """
        if cmds.nodeType(node) != "transform":
            return False

        children = cmds.listRelatives(node, c=True)
        if not children:
            return True

        for c in children:
            if cmds.nodeType(c) != 'transform':
                return False
        else:
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
        print item.properties
        all_dag_nodes = cmds.ls(dag=True, sn=True)
        groups = [g for g in all_dag_nodes if self._is_group(g)]
        status = True
        status = self._node_naming(_group_nodes, groups) and status
        status = self._camera_naming(_group_nodes) and status

        print "status", status
        if not status:
            return status

        return super(MayaPublishFilesDDIntegValidationPlugin, self).validate(task_settings, item)
