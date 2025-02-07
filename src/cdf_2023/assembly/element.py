from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import math

from compas.datastructures import Mesh
from compas.datastructures import mesh_transform

from compas.geometry import Frame, Vector, Line, Point
from compas.geometry import Box
from compas.geometry import Transformation, Translation, Rotation
from compas.geometry import cross_vectors
from compas.geometry import normalize_vector
from compas.geometry import centroid_polyhedron
from compas.geometry import volume_polyhedron
from compas_rhino.geometry import RhinoNurbsSurface
from compas.datastructures import Mesh, mesh_transform


from .utilities import _deserialize_from_data
from .utilities import _serialize_to_data


__all__ = ['Element']


class Element(object):
    """Data structure representing a discrete element of an assembly.

    Attributes
    ----------
    _frame : :class:`compas.geometry.Frame`
        The frame of the element.

    _tool_frame : :class:`compas.geometry.Frame`
        The frame of the element where the robot's tool should attach to.

    _source : :class:`compas.geometry.Shape`
        The source geometry of the element, e.g., `compas.geometry.Box`.

    _mesh : :class:`compas.geometry.Mesh`
        The mesh geometry of the element.

    trajectory : :class:`compas_fab.robots.JointTrajectory`
        The robot trajectory in joint space.

    path : :list: :class:`compas.geometry.Frame`
        The robot tool path in cartesian space.

    Examples
    --------
    >>> from compas.datastructures import Mesh
    >>> from compas.geometry import Box
    >>> element = Element.from_box(Box(Frame.worldXY(), ))

    """

    def __init__(self, frame):
        super(Element, self).__init__()

        self.message = "dynamic_cylinder"
        self.type = "object"
        self.connector_frame_1 = None
        self.connector_frame_2 = None
        self.connector_range_1 = None
        self.connector_range_2 = None
        self.connector_1_state = True
        self.connector_2_state = True
        self.joint_frame_1 = None
        self.joint_frame_2 = None
        self.line = None
        self._type = ''
        self._base_frame = None

        self.frame = frame
        self._tool_frame = None

        self._source = None
        self._mesh = None

        self.RCF = None
        self.trajectory = None
        self.path = []

    @classmethod
    def from_mesh(cls, mesh, frame):
        """Construct an element from a mesh.

        Parameters
        ----------
        mesh : :class:`Mesh`
            Mesh datastructure.
        frame : :class:`Frame`
            Origin frame of the element.

        Returns
        -------
        :class:`Element`
            New instance of element.
        """
        element = cls(frame)
        element._source = element._mesh = mesh
        return element

    @classmethod
    def from_shape(cls, shape, frame):
        """Construct an element from a shape primitive.

        Parameters
        ----------
        shape : :class:`compas.geometry.Shape`
            Shape primitive describing the element.
        frame : :class:`Frame`
            Origin frame of the element.

        Returns
        -------
        :class:`Element`
            New instance of element.
        """
        element = cls(frame)
        element._source = shape
        element._mesh = Mesh.from_shape(element._source)
        return element

    @classmethod
    def from_box(cls, box):
        """Construct an element from a box primitive.

        Parameters
        ----------
        box : :class:`compas.geometry.Box`
            Box primitive describing the element.

        Returns
        -------
        :class:`Element`
            New instance of element.
        """
        return cls.from_shape(box, box.frame)

    @classmethod
    def from_dimensions(cls, length, width, height):
        """Construct an element with a box primitive with the given dimensions.

        Parameters
        ----------
        length : float
            length of the box.
        width : float
            width of the box.
        height : float
            height of the box.
        Returns
        -------
        :class:`Element`
            New instance of element.
        """

        frame = Frame([0., 0., height/2], [1, 0, 0], [0, 1, 0])  # center of the box frame
        box = Box(frame, length, width, height)
        return cls.from_shape(box, frame)

    @classmethod
    def from_polysurface(cls, guid, frame):
        """Class method for constructing a block from a Rhino poly-surface.

        Parameters
        ----------
        guid : str
            The GUID of the poly-surface.
        frame : :class:`Frame`
            Origin frame of the element.
        Notes
        -----
        In Rhino, poly-surfaces are organised such that the cycle directions of
        the individual sub-surfaces produce normal vectors that point out of the
        enclosed volume. The normal vectors of the faces of the mesh, therefore
        also point "out" of the enclosed volume.
        """
        from compas_rhino.geometry import RhinoSurface
        element = cls(frame)
        element._source = RhinoSurface.from_guid(guid)
        element._mesh = element._source.brep_to_compas()
        return element

    @classmethod
    def from_rhinomesh(cls, guid, frame):
        """Class method for constructing a block from a Rhino mesh.

        Parameters
        ----------
        guid : str
            The GUID of the mesh.
        frame : :class:`Frame`
            Origin frame of the element.
        """
        from compas_rhino.geometry import RhinoMesh
        element = cls(frame)
        element._source = RhinoMesh.from_guid(guid)
        element._mesh = element._source.mesh.to_compas()
        return element

    @property
    def mesh(self):
        """Mesh of the element."""
        if not self._source:
            return None

        if self._mesh:
            return self._mesh

        if isinstance(self._source, Mesh):
            self._mesh = self._source
        else:
            self._mesh = Mesh.from_shape(self._source)

        return self._mesh

    @mesh.setter
    def mesh(self, mesh):
        self._source = self._mesh = mesh

    @property
    def frame(self):
        """Frame of the element."""
        return self._frame

    @frame.setter
    def frame(self, frame):
        self._frame = frame.copy()

    @property
    def tool_frame(self):
        """tool frame of the element"""
        if not self._tool_frame:
            self._tool_frame = self.frame.copy()

        return self._tool_frame

    @tool_frame.setter
    def tool_frame(self, frame):
        self._tool_frame = frame.copy()

    @property
    def tool_frame_pose_quaternion(self):
        """ formats the element's tool frame to a pose quaternion and returns the pose"""
        return list(self.tool_frame.point) + list(self.tool_frame.quaternion)

    @tool_frame_pose_quaternion.setter
    def tool_frame_pose_quaternion(self, pose_quaternion):
        self.tool_frame = Frame.from_quaternion(pose_quaternion[3:], point=pose_quaternion[:3])

    @property
    def centroid(self):
        return self._mesh.centroid()

    @property
    def face_frames(self):
        """Compute the local frame of each face of the element's mesh.

        Returns
        -------
        dict
            A dictionary mapping face identifiers to face frames.
        """
        return {fkey: self.face_frame(fkey) for fkey in self._mesh.faces()}

    def face_frame(self, fkey):
        """Compute the frame of a specific face.

        Parameters
        ----------
        fkey : hashable
            The identifier of the frame.

        Returns
        -------
        frame
            The frame of the specified face.
        """
        xyz = self._mesh.face_coordinates(fkey)
        o = self._mesh.face_center(fkey)
        w = self._mesh.face_normal(fkey)
        u = [xyz[1][i] - xyz[0][i] for i in range(3)]  # align with longest edge instead?
        v = cross_vectors(w, u)
        uvw = normalize_vector(u), normalize_vector(v), normalize_vector(w)
        return o, uvw

    @property
    def top(self):
        """Identify the *top* face of the element's mesh.

        Returns
        -------
        int
            The identifier of the face.

        Notes
        -----
        The face with the highest centroid is considered the *top* face.
        """
        fkey_centroid = {fkey: self._mesh.face_center(fkey) for fkey in self._mesh.faces()}
        fkey, _ = sorted(fkey_centroid.items(), key=lambda x: x[1][2])[-1]
        return fkey

    @property
    def center(self):
        """Compute the center of mass of the element.

        Returns
        -------
        point
            The center of mass of the element.
        """
        vertices = [self._mesh.vertex_coordinates(key) for key in self._mesh.vertices()]
        faces = [self._mesh.face_vertices(fkey) for fkey in self._mesh.faces()]
        return centroid_polyhedron((vertices, faces))

    @property
    def volume(self):
        """Compute the volume of the element.

        Returns
        -------
        float
            The volume of the element.
        """
        vertices = [self._mesh.vertex_coordinates(key) for key in self._mesh.vertices()]
        faces = [self._mesh.face_vertices(fkey) for fkey in self._mesh.faces()]
        v = volume_polyhedron((vertices, faces))
        return v

    @classmethod
    def from_data(cls, data):
        """Construct an element from its data representation.

        Parameters
        ----------
        data : :obj:`dict`
            The data dictionary.

        Returns
        -------
        Element
            The constructed element.
        """
        element = cls(Frame.worldXY())
        element.data = data
        return element

    @property
    def data(self):
        """Returns the data dictionary that represents the element.

        Returns
        -------
        dict
            The element data.

        Examples
        --------
        >>> element = Element(Frame.worldXY())
        >>> print(element.data)
        """
        d = dict(frame=self.frame.to_data())

        # Only include gripping plane if attribute is really set
        # (unlike the property getter that defaults to `self.frame`)
        if self._tool_frame:
            d['_tool_frame'] = self._tool_frame.to_data()

        if self._source:
            d['_source'] = _serialize_to_data(self._source)

        if self._mesh:
            #d['_mesh'] = _serialize_to_data(self._mesh)
            d['_mesh'] = self._mesh.to_data()

        if self.trajectory:
            d['trajectory'] = [f.to_data() for f in self.trajectory]

        if self.path:
            d['path'] = [f.to_data() for f in self.path]

        if self.connector_frame_1:
            d['connector_frame_1'] = self.connector_frame_1.to_data()

        if self.connector_frame_2:
            d['connector_frame_2'] = self.connector_frame_2.to_data()

        if self.connector_range_1:
            d['connector_range_1'] = self.connector_range_1.to_data()

        if self.connector_range_2:
            d['connector_range_2'] = self.connector_range_2.to_data()

        d['connector_1_state'] = self.connector_1_state

        d['connector_2_state'] = self.connector_2_state

        if self.line:
            d['line'] = self.line.to_data()

        if self.joint_frame_1:
            d['joint_frame_1'] = self.joint_frame_1.to_data()

        if self.joint_frame_2:
            d['joint_frame_2'] = self.joint_frame_2.to_data()

        if self._type:
            d['_type'] = self._type

        if self._base_frame:
            d['_base_frame'] = self._base_frame.to_data()

        if self.RCF:
            d['RCF'] = self.RCF.to_data()

        return d

    @data.setter
    def data(self, data):
        self.frame = Frame.from_data(data['frame'])
        if '_tool_frame' in data:
            self.tool_frame = Frame.from_data(data['_tool_frame'])
        if '_source' in data:
            self._source = _deserialize_from_data(data['_source'])
        if '_mesh' in data:
            #self._mesh = _deserialize_from_data(data['_mesh'])
            self._mesh = Mesh.from_data(data['_mesh'])
        if 'trajectory' in data:
            from compas_fab.robots import JointTrajectory
            self.trajectory = [JointTrajectory.from_data(d) for d in data['trajectory']]
            #self.trajectory = _deserialize_from_data(data['trajectory'])
        if 'path' in data:
            self.path = [Frame.from_data(d) for d in data['path']]
        if 'connector_frame_1' in data:
            self.connector_frame_1 = Frame.from_data(data['connector_frame_1'])
        if 'connector_frame_2' in data:
            self.connector_frame_2 = Frame.from_data(data['connector_frame_2'])
        if 'connector_range_1' in data:
            self.connector_range_1 = RhinoNurbsSurface.from_data(data['connector_range_1'])
        if 'connector_range_2' in data:
            self.connector_range_2 = RhinoNurbsSurface.from_data(data['connector_range_2'])
        if 'connector_1_state' in data:
            self.connector_1_state = data['connector_1_state']
        if 'connector_2_state' in data:
            self.connector_2_state = data['connector_2_state']
        if 'line' in data:
            self.line = Line.from_data(data['line'])
        if 'joint_frame_1' in data:
            self.joint_frame_1 = Frame.from_data(data['joint_frame_1'])
        if 'joint_frame_2' in data:
            self.joint_frame_2 = Frame.from_data(data['joint_frame_2'])
        if '_type' in data:
            self._type = data['_type']
        if '_base_frame' in data:
            self._base_frame = Frame.from_data(data['_base_frame'])
        if 'RCF' in data:
            self.RCF = Frame.from_data(data['RCF'])

    def to_data(self):
        """Returns the data dictionary that represents the element.

        Returns
        -------
        dict
            The element data.

        Examples
        --------
        >>> from compas.geometry import Frame
        >>> e1 = Element(Frame.worldXY())
        >>> e2 = Element.from_data(element.to_data())
        >>> e2.frame == Frame.worldXY()
        True
        """
        return self.data

    def transform(self, transformation):
        """Transforms the element.

        Parameters
        ----------
        transformation : :class:`Transformation`

        Returns
        -------
        None

        Examples
        --------
        >>> from compas.geometry import Box
        >>> from compas.geometry import Translation
        >>> element = Element.from_box(Box(Frame.worldXY(), 1, 1, 1))
        >>> element.transform(Translation.from_vector([1, 0, 0]))
        """
        self.frame.transform(transformation)
        if self._tool_frame:
            self.tool_frame.transform(transformation)
        if self.connector_frame_1:
            self.connector_frame_1.transform(transformation)
        if self.connector_frame_2:
            self.connector_frame_2.transform(transformation)
        if self.connector_range_1:
            self.connector_range_1.transform(transformation)
        if self.connector_range_2:
            self.connector_range_2.transform(transformation)
        if self.line:
            self.line.transform(transformation)
        if self.joint_frame_1:
            self.joint_frame_1.transform(transformation)
        if self.joint_frame_2:
            self.joint_frame_2.transform(transformation)
        if self._base_frame:
            self._base_frame.transform(transformation)
        if self.RCF:
            self.RCF.transform(transformation)
        if self._source:
            if type(self._source) == Mesh:
                mesh_transform(self._source, transformation)  # it would be really good to have Mesh.transform()
            else:
                self._source.transform(transformation)
        if self._mesh:
            mesh_transform(self._mesh, transformation)  # it would be really good to have Mesh.transform()
        if self.path:
            [f.transform(transformation) for f in self.path]

    def transformed(self, transformation):
        """Returns a transformed copy of this element.

        Parameters
        ----------
        transformation : :class:`Transformation`

        Returns
        -------
        Element

        Examples
        --------
        >>> from compas.geometry import Box
        >>> from compas.geometry import Translation
        >>> element = Element.from_box(Box(Frame.worldXY(), 1, 1, 1))
        >>> element2 = element.transformed(Translation.from_vector([1, 0, 0]))
        """
        elem = self.copy()
        elem.transform(transformation)
        return elem

    def copy(self):
        """Returns a copy of this element.

        Returns
        -------
        Element
        """
        elem = Element(self.frame.copy())
        if self._tool_frame:
            elem.tool_frame = self.tool_frame.copy()
        if self.connector_frame_1:
            elem.connector_frame_1 = self.connector_frame_1.copy()
        if self.connector_frame_2:
            elem.connector_frame_2 = self.connector_frame_2.copy()
        if self.connector_range_1:
            elem.connector_range_1 = self.connector_range_1.copy()
        if self.connector_range_2:
            elem.connector_range_2 = self.connector_range_2.copy()
        if self.connector_1_state:
            elem.connector_1_state = self.connector_1_state
        if self.connector_2_state:
            elem.connector_2_state = self.connector_2_state
        if self.line:
            elem.line = self.line.copy()
        if self.joint_frame_1:
            elem.joint_frame_1 = self.joint_frame_1.copy()
        if self.joint_frame_2:
            elem.joint_frame_2 = self.joint_frame_2.copy()
        if self._type:
            elem._type = self._type
        if self._base_frame:
            elem._base_frame = self._base_frame.copy()
        if self.RCF:
            elem.RCF = self.RCF.copy()
        if self._source:
            elem._source = self._source.copy()
        if self._mesh:
            elem._mesh = self._mesh.copy()
        if self.path:
            elem.path = [f.copy() for f in self.path]

        return elem

    def get_pose_quaternion(self):
        """ formats the element's frame to a pose quaternion and returns the pose"""
        return list(self.frame.point) + list(self.frame.quaternion)

    def connectors(self, state='all'):
        """ Create a list containing the connector_frames of an element.
        """
        connector_frames = []

        if state == 'all':
            return self.connector_frame_1, self.connector_frame_2
        elif state == 'open':
            if self.connector_1_state:
                connector_frames.append(self.connector_frame_1)
            if self.connector_2_state:
                connector_frames.append(self.connector_frame_2)
            return connector_frames
        elif state == 'closed':
            if not self.connector_1_state:
                connector_frames.append(self.connector_frame_1)
            if not self.connector_2_state:
                connector_frames.append(self.connector_frame_2)
            return connector_frames
        else:
            return []

    def connectors_ranges(self, state='all'):
        """ Create a list containing the connectors_ranges of an element.
        """
        connectors_ranges= []

        if state == 'all':
            return self.connector_range_1, self.connector_range_2
        elif state == 'open':
            if self.connector_1_state:
                connectors_ranges.append(self.connector_range_1)
            if self.connector_2_state:
                connectors_ranges.append(self.connector_range_2)
            return connectors_ranges
        elif state == 'closed':
            if not self.connector_1_state:
                connectors_ranges.append(self.connector_range_1)
            if not self.connector_2_state:
                connectors_ranges.append(self.connector_range_2)
            return connectors_ranges
        else:
            return []

    def current_option_elements(self, assembly, flip, angle, shift_value):

        radius = assembly.globals['rod_radius']
        length = assembly.globals['rod_length']
        rf_unit_radius = assembly.globals['rf_unit_radius']
        rf_unit_offset = assembly.globals['rf_unit_offset']

        option_elements = []
        #length = self._source.height

        current_connector_frame = None

        if self.connector_1_state == True:
            current_connector_frame = self.connector_frame_1
            c = -1
        if self.connector_2_state == True:
            current_connector_frame = self.connector_frame_2
            c = 1

        if flip == 'AA':
            a = b = 0
        if flip == 'AB':
            a = 0
            b = 1*c
        if flip == 'BA':
            a = 1*c
            b = 0
        if flip == 'BB':
            a = b = 1*c

        if current_connector_frame != None:
            R1 = Rotation.from_axis_and_angle(current_connector_frame.zaxis, math.radians(120), current_connector_frame.point)
            R2 = Rotation.from_axis_and_angle(current_connector_frame.zaxis, math.radians(240), current_connector_frame.point)
            e1 = self.transformed(R1)
            e2 = self.transformed(R2)

            # T_point = Translation.from_vector(self.frame.xaxis)
            # new_point = self.frame.point.transformed(T_point)
            R3 = Rotation.from_axis_and_angle(self.frame.xaxis, math.radians(angle),self.frame.point)

            T1 = Translation.from_vector(-e1.frame.xaxis*a*((length-rf_unit_radius+rf_unit_offset)/2.))
            T2 = Translation.from_vector(-e2.frame.xaxis*b*((length-rf_unit_radius+rf_unit_offset)/2.))

            T3 = Translation.from_vector(self.frame.xaxis * shift_value)

            e1.transform(R3*T1*T3)
            e2.transform(R3*T2*T3)

            option_elements.append(e1)
            option_elements.append(e2)

        # if current_connector_frame != None:
        #         T = Translation.from_vector(self.frame.xaxis * shift_value)
        #         R = Rotation.from_axis_and_angle(self.frame.xaxis, math.radians(angle),self.frame.point)

        #         current_connector_frame.transform(T*R)

        #         R1 = Rotation.from_axis_and_angle(current_connector_frame.zaxis, math.radians(120), current_connector_frame.point)
        #         R2 = Rotation.from_axis_and_angle(current_connector_frame.zaxis, math.radians(240), current_connector_frame.point)
        #         e1 = self.transformed(R1)
        #         e2 = self.transformed(R2)

        #         # T_point = Translation.from_vector(self.frame.xaxis)
        #         # new_point = self.frame.point.transformed(T_point)

        #         T1 = Translation.from_vector(-e1.frame.xaxis*a*((length-rf_unit_radius+rf_unit_offset)/2.))
        #         T2 = Translation.from_vector(-e2.frame.xaxis*b*((length-rf_unit_radius+rf_unit_offset)/2.))

        #         #e1.transform(T1)
        #         #e2.transform(T2)

        #         option_elements.append(e1)
        #         option_elements.append(e2)

        return option_elements

    def current_option_vectors(self, len):

        vector_vertical_offset = 0.01

        current_option_vectors = []
        if self.connector_1_state == True:
            p = self.connector_frame_1.point + Vector.Zaxis()*vector_vertical_offset
            T1 = Translation.from_vector(self.frame.xaxis*self._source.diameter/2.*1)
            T2 = Translation.from_vector(self.frame.xaxis*len)
            current_option_vectors.append((p.transformed(T1), Vector.from_start_end(p.transformed(T1), p.transformed(T2))))

        if self.connector_2_state == True:
            p = self.connector_frame_2.point + Vector.Zaxis()*vector_vertical_offset
            T1 = Translation.from_vector(self.frame.xaxis*self._source.diameter/2.*-1)
            T2 = Translation.from_vector(self.frame.xaxis*-len)
            current_option_vectors.append((p.transformed(T1), Vector.from_start_end(p.transformed(T1), p.transformed(T2))))

        if current_option_vectors:
            return current_option_vectors
        else:
            return []

    def current_option_viz(self, rf_unit_radius):

        vector_vertical_offset = 0.01

        current_option_frames = []
        if self.connector_1_state == True:
            p = self.connector_frame_1.point + Vector.Zaxis()*vector_vertical_offset
            T = Translation.from_vector(self.connector_frame_1.yaxis*rf_unit_radius/2.)
            current_option_frames.append(Frame(p, self.connector_frame_1.xaxis, self.connector_frame_1.yaxis).transformed(T))

        if self.connector_2_state == True:
            p = self.connector_frame_2.point + Vector.Zaxis()*vector_vertical_offset
            T = Translation.from_vector(self.connector_frame_2.yaxis*rf_unit_radius/2.)
            current_option_frames.append(Frame(p, self.connector_frame_2.xaxis, self.connector_frame_2.yaxis).transformed(T))

        if current_option_frames:
            return current_option_frames
        else:
            return []
