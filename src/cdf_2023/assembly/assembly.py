from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import os
import math
import compas

from copy import deepcopy
from compas.geometry import Frame, Vector, Plane
from compas.geometry import Transformation, Translation, Rotation
from compas.geometry import intersection_line_plane
from compas.geometry import distance_point_point, distance_line_line, distance_point_line
from compas.datastructures import Network, mesh_offset
from compas.artists import Artist
from compas.colors import Color
from compas.topology import connected_components
from compas_rhino.conversions import line_to_rhino_curve, point_to_compas, point_to_rhino, line_to_compas

import rhinoscriptsyntax as rs
import Rhino.Geometry as rg
import ghpythonlib.components as gh

from .element import Element

from .utilities import FromToData
from .utilities import FromToJson
from .utilities import element_to_INCON
from .utilities import tag_to_INCON

__all__ = ['Assembly']



class Assembly(FromToData, FromToJson):
    """A data structure for discrete element assemblies.

    An assembly is essentially a network of assembly elements.
    Each element is represented by a node of the network.
    Each interface or connection between elements is represented by an edge of the network.

    Attributes
    ----------
    network : :class:`compas.Network`, optional
    elements : list of :class:`Element`, optional
        A list of assembly elements.
    attributes : dict, optional
        User-defined attributes of the assembly.
        Built-in attributes are:
        * name (str) : ``'Assembly'``
    default_element_attribute : dict, optional
        User-defined default attributes of the elements of the assembly.
        The built-in attributes are:
        * is_planned (bool) : ``False``
        * is_placed (bool) : ``False``
    default_connection_attributes : dict, optional
        User-defined default attributes of the connections of the assembly.

    Examples
    --------
    >>> assembly = Assembly()
    >>> for i in range(2):
    >>>     element = Element.from_box(Box(Frame.worldXY(), 10, 5, 2))
    >>>     assembly.add_element(element)
    """

    def __init__(self,
                 elements=None,
                 attributes=None,
                 default_element_attributes=None,
                 default_connection_attributes=None):

        self.network = Network()
        self.network.attributes.update({
            'name' : 'Assembly'})

        if attributes is not None:
            self.network.attributes.update(attributes)

        self.network.default_node_attributes.update({
            'elem_type' : 1,
            'is_planned': False,
            'is_built' : False,
            'placed_by' : 'human',
            'is_support' : False,
            'robot_name' : 'AA',
            'is_held_by_robot' : False,
            'robot_AA_base_frame' : False,
            'robot_AB_base_frame' : False,
            'frame_measured':False

        })

        if default_element_attributes is not None:
            self.network.default_node_attributes.update(default_element_attributes)

        if default_connection_attributes is not None:
            self.network.default_edge_attributes.update(default_connection_attributes)

        if elements:
            for element in elements:
                self.add_element(element)

    @property
    def name(self):
        """str : The name of the assembly."""
        return self.network.attributes.get('name', None)

    @name.setter
    def name(self, value):
        self.network.attributes['name'] = value

    def number_of_elements(self):
        """Compute the number of elements of the assembly.

        Returns
        -------
        int
            The number of elements.

        """
        return self.network.number_of_nodes()

    def number_of_connections(self):
        """Compute the number of connections of the assembly.

        Returns
        -------
        int
            the number of connections.

        """
        return self.network.number_of_edges()

    @property
    def data(self):
        """Return a data dictionary of the assembly.
        """
        # Network data does not recursively serialize to data...
        d = self.network.data

        # so we need to trigger that for elements stored in nodes
        node = {}
        for vkey, vdata in d['node'].items():
            node[vkey] = {key: vdata[key] for key in vdata.keys() if key != 'element'}
            node[vkey]['element'] = vdata['element'].to_data()

            if 'frame_measured' in vdata:
                if node[vkey]['frame_measured']:
                    node[vkey]['frame_measured'] = node[vkey]['frame_measured'].to_data()

            if 'robot_AA_base_frame' in vdata:
                if node[vkey]['robot_AA_base_frame']:
                    node[vkey]['robot_AA_base_frame'] = node[vkey]['robot_AA_base_frame'].to_data()

            if 'robot_AB_base_frame' in vdata:
                if node[vkey]['robot_AB_base_frame']:
                    node[vkey]['robot_AB_base_frame'] = node[vkey]['robot_AB_base_frame'].to_data()

        d['node'] = node

        return d

    @data.setter
    def data(self, data):
        # Deserialize elements from node dictionary
        for _vkey, vdata in data['node'].items():
            vdata['element'] = Element.from_data(vdata['element'])

            if 'frame_measured' in vdata:
                if vdata['frame_measured']:
                    vdata['frame_measured'] = Frame.from_data(vdata['frame_measured']) #node[vkey]['frame_measured'].to_data()

            if 'robot_AA_base_frame' in vdata:
                if vdata['robot_AA_base_frame']:
                    vdata['robot_AA_base_frame'] = Frame.from_data(vdata['robot_AA_base_frame']) #node[vkey]['frame_measured'].to_data()

            if 'robot_AB_base_frame' in vdata:
                if vdata['robot_AB_base_frame']:
                    vdata['robot_AB_base_frame'] = Frame.from_data(vdata['robot_AB_base_frame']) #node[vkey]['frame_measured'].to_data()

        self.network = Network.from_data(data)

    def clear(self):
        """Clear all the assembly data."""
        self.network.clear()

    def add_element(self, element, key=None, attr_dict={}, **kwattr):
        """Add an element to the assembly.

        Parameters
        ----------
        element : Element
            The element to add.
        attr_dict : dict, optional
            A dictionary of element attributes. Default is ``None``.

        Returns
        -------
        hashable
            The identifier of the element.
        """
        attr_dict.update(kwattr)
        x, y, z = element.frame.point
        key = self.network.add_node(key=key, attr_dict=attr_dict,
                                    x=x, y=y, z=z, element=element)
        return key


    def add_rf_unit_element(
            self,
            current_key,
            flip='AA',
            angle=0,
            shift_value=0,
            placed_by='human',
            robot_name = 'AA',
            robot_AA_base_frame = None,
            robot_AB_base_frame = None,
            on_ground=False,
            unit_index=0,
            frame_measured=None
        ):
        """Add an element to the assembly.
        """
        radius = self.globals['rod_radius']
        length = self.globals['rod_length']
        rf_unit_radius = self.globals['rf_unit_radius']
        rf_unit_offset = self.globals['rf_unit_offset']

        N = self.network.number_of_nodes()

        current_elem = self.network.node[current_key]['element']

        # Find the open connector of the current element
        if current_elem.connector_1_state:
            current_connector_frame = current_elem.connector_frame_1
            c = -1
        else:
            current_connector_frame = current_elem.connector_frame_2
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

        new_elem = current_elem.copy()

        if placed_by == 'robot':
            R1 = Rotation.from_axis_and_angle(current_connector_frame.zaxis, math.radians(120), current_connector_frame.point)
            T1 = Translation.from_vector(-new_elem.frame.xaxis*a*((length-rf_unit_radius+rf_unit_offset)/2.))
        else:
            R1 = Rotation.from_axis_and_angle(current_connector_frame.zaxis, math.radians(240), current_connector_frame.point)
            T1 = Translation.from_vector(-new_elem.frame.xaxis*b*((length-rf_unit_radius+rf_unit_offset)/2.))

        new_elem.transform(R1*T1)

        # Define a desired rotation around the parent element
        T_point = Translation.from_vector(current_elem.frame.xaxis)
        new_point = current_elem.frame.point.transformed(T_point)
        R2 = Rotation.from_axis_and_angle(current_elem.frame.xaxis, math.radians(angle), new_point)

        # Define a desired shift value along the parent element
        T3 = Translation.from_vector(current_elem.frame.xaxis*shift_value)

        # Transform the new element
        new_elem.transform(R2*T3)

        self.add_element(new_elem,
                         placed_by=placed_by,
                         robot_name=robot_name,
                         robot_AA_base_frame=robot_AA_base_frame,
                         robot_AB_base_frame=robot_AB_base_frame,
                         on_ground=on_ground,
                         frame_measured=frame_measured,
                         is_planned=True,
                         is_built=False,
                         is_support=False)

        # Add adges
        if unit_index == 0:
            self.network.add_edge(current_key, N, edge_to='neighbour')
        else:
            self.network.add_edge(N-1, N, edge_to='parent')
            self.network.add_edge(current_key, N, edge_to='parent')

        self.update_connectors_states(current_key, flip, new_elem, unit_index)

        if unit_index == 1:
            if current_elem.connector_1_state:
                current_elem.connector_1_state = False
            else:
                current_elem.connector_2_state = False

        return new_elem

    def add_connection(self, u, v, attr_dict=None, **kwattr):
        """Add a connection between two elements and specify its attributes.

        Parameters
        ----------
        u : hashable
            The identifier of the first element of the connection.
        v : hashable
            The identifier of the second element of the connection.
        attr_dict : dict, optional
            A dictionary of connection attributes.
        kwattr
            Other connection attributes as additional keyword arguments.

        Returns
        -------
        tuple
            The identifiers of the elements.
        """
        return self.network.add_edge(u, v, attr_dict, **kwattr)

    def add_joint(self, edge, joint):
        """
        """
        u, v = edge
        return self.add_edge(u, v, joint=joint)

    def transform(self, transformation):
        """Transforms this assembly.

        Parameters
        ----------
        transformation : :class:`Transformation`

        Returns
        -------
        None
        """
        for _k, element in self.elements(data=False):
            element.transform(transformation)

    def transformed(self, transformation):
        """Returns a transformed copy of this assembly.

        Parameters
        ----------
        transformation : :class:`Transformation`

        Returns
        -------
        Assembly
        """
        assembly = self.copy()
        assembly.transform(transformation)
        assembly.network.transform(transformation)
        return assembly

    def copy(self):
        """Returns a copy of this assembly.
        """
        cls = type(self)
        return cls.from_data(deepcopy(self.data))

    def element(self, key, data=False):
        """Get an element by its key."""
        if data:
            return self.network.node[key]['element'], self.network.node[key]
        else:
            return self.network.node[key]['element']

    def elements(self, data=False):
        """Iterate over the elements of the assembly.

        Parameters
        ----------
        data : bool, optional
            If ``True``, yield both the identifier and the attributes.

        Yields
        ------
        2-tuple
            The next element as a (key, element) tuple, if ``data`` is ``False``.
        3-tuple
            The next element as a (key, element, attr) tuple, if ``data`` is ``True``.

        """
        if data:
            for vkey, vattr in self.network.nodes(True):
                yield vkey, vattr['element'], vattr
        else:
            for vkey in self.network.nodes(data):
                yield vkey, self.network.node[vkey]['element']

    def connections(self, data=False):
        """Iterate over the connections of the network.

        Parameters
        ----------
        data : bool, optional
            If ``True``, yield both the identifier and the attributes.

        Yields
        ------
        2-tuple
            The next connection identifier (u, v), if ``data`` is ``False``.
        3-tuple
            The next connection as a (u, v, attr) tuple, if ``data`` is ``True``.

        """
        return self.network.edges(data)

    def shortest_distance_between_two_lines(self, line1, line2):

        # l1 = line_to_compas(line1)
        # l2 = line_to_compas(line2)

        # d = distance_line_line(l1, l2)
        # return d
        a, b, d = gh.CurveProximity(line1, line2)
        return d

    def collision_check(self, current_key, option_elems, tolerance):
        """Check for collisions with previously built elements.
        """

        collision = False
        results = []
        dist_list = []
        for key, elem in self.elements():
            if key != current_key:
                line1 = Artist(elem.line).draw()
                for option_elem in option_elems:
                    line2 = Artist(option_elem.line).draw()
                    #results.append(True if distance_line_line(elem.line, option_elem.line, tol = 0.001) < assembly.globals['rod_radius']*2. + tolerance else False)
                    distance = self.shortest_distance_between_two_lines(line1, line2)
                    results.append(True if distance < (self.globals['rod_radius'] * 2. + 0.015 + tolerance) else False)
                    dist_list.append(distance)
                collision = True if True in results else False
                dist = min(dist_list)
        return collision, dist

    def check_ground_collision(self, option_elems):
        """Check if an element touches the ground.
        """

        ground_plane = Plane.from_frame(Frame.worldXY())

        for option in option_elems:
            intersection = intersection_line_plane(option.line, ground_plane)
            if intersection != None:
                return intersection

    def get_rot_angle(self, step, rot_axis, rot_point, elem_line1, elem_line2, rot_dir, epsilon):
        """
        elem_line1: element to rotate
        elem_line2: element to attach to
        """

        rot_angle = 0
        init_step = math.radians(step)
        alpha = init_step

        if rot_dir == 0:
            alpha = -alpha

        i = 0
        max_i = 25

        d = self.shortest_distance_between_two_lines(elem_line1, elem_line2)

        while d < self.globals['rod_radius'] * 2.0 + 0.015:
            i += 1

            if i >= max_i:
                break

            rot_angle += alpha

            # rotate the cylinder axis by alpha
            R = rg.Transform.Rotation(alpha, rot_axis, rot_point)
            elem_line1.Transform(R)

            d = self.shortest_distance_between_two_lines(elem_line1, elem_line2)

        i = 0
        max_i= 50
        d = self.shortest_distance_between_two_lines(elem_line1, elem_line2)

        while abs(d - (self.globals['rod_radius'] * 2.0 + 0.015)) > epsilon:
            i += 1

            if i >= max_i:
                break

            # half the rotation step and ensure it is > 0
            alpha = abs(0.5 * alpha)

            if rot_dir == 0:
                alpha = -alpha   # invert direction for counter clockwise rotation

            # test distance
            d = self.shortest_distance_between_two_lines(elem_line1, elem_line2)
            if d > self.globals['rod_radius'] * 2.0 + 0.015:
                alpha = -alpha   # distance too large --> rotate back
            else:
                alpha = alpha   # distance too small --> rotate in same direction

            # rotate axis
            R = rg.Transform.Rotation(alpha, rot_axis, rot_point)
            elem_line1.Transform(R)

            rot_angle += alpha

        return math.degrees(rot_angle)

    def add_third_element(self, elem, elem1, elem2, point1, point2, shift_value, epsilon):
        """
        elem1: open connector
        elem2: option elem
        """

        elem1_line_rg = line_to_rhino_curve(elem1.line)
        elem2_line_rg = line_to_rhino_curve(elem2.line)

        param1 = elem2_line_rg.NormalizedLengthParameter(point1)
        param2 = elem1_line_rg.NormalizedLengthParameter(point2)

        start_point = elem1_line_rg.PointAt(param1[1])
        end_point = elem2_line_rg.PointAt(param2[1])

        elem_x_vector = rg.Vector3d(end_point - start_point)
        elem_y_vector = elem_x_vector.Clone()
        elem_y_vector.Rotate(math.radians(90), rg.Vector3d.XAxis)

        elem_frame = Frame(point_to_compas(start_point), Vector(elem_x_vector.X, elem_x_vector.Y, elem_x_vector.Z), Vector(elem_y_vector.X, elem_y_vector.Y, elem_y_vector.Z))

        T1 = Transformation.from_frame_to_frame(Frame.worldXY(), elem_frame)
        new_elem = elem.transformed(T1)
        T2 = Translation.from_vector(elem_frame.xaxis * shift_value)
        new_elem.transform(T2)

        rot_dir1 = 0
        rot_dir2 = 1
        step1 = 0.3
        step2 = 0.3

        rot_axis1 = rg.Vector3d(elem2_line_rg.PointAtStart- elem2_line_rg.PointAtEnd)
        rot_axis2 = rg.Vector3d(elem1_line_rg.PointAtStart - elem1_line_rg.PointAtEnd)
        rot_point1 = point_to_rhino(elem2.frame.point)
        rot_point2 = point_to_rhino(elem1.frame.point)
        new_elem_line = line_to_rhino_curve(new_elem.line)

        tol_angle1 = self.get_rot_angle(step1, rot_axis1, rot_point1, new_elem_line, elem1_line_rg, rot_dir1, epsilon)
        tol_angle2 = self.get_rot_angle(step2, rot_axis2, rot_point2, new_elem_line, elem2_line_rg, rot_dir2, epsilon)

        R1 = Rotation.from_axis_and_angle(elem2.frame.xaxis, math.radians(tol_angle1), elem2.frame.point)
        R2 = Rotation.from_axis_and_angle(elem1.frame.xaxis, math.radians(tol_angle2), elem1.frame.point)
        new_elem.transform(R1)
        new_elem.transform(R2)

        return new_elem

    def calculate_global_equilibrium(self, support, option_elems, radius, allow_temp_support=True):
        """Check if the structure is in equilibrium.
        """
        static_equilibrium = []
        supports = []
        vol = []
        cen = []

        if allow_temp_support == True:
            s_glob = True

        e = [element.line for key, element in self.elements()]
        e += [elem_option.line for elem_option in option_elems]

        supports.append(support)
        supports.extend(e)
        e = supports

        for i, element in enumerate(e):
            if i == 0:
                #print element
                voll = rs.SurfaceVolume(element)[0] # volume Vector of base; Material weight is considered as constant; Input as Brep
                cenl = rs.SurfaceVolumeCentroid(element)[0] # center node
                cenl = (cenl[0], cenl[1], 0) # planar Center-nodes
            else:
                voll = element.length *  math.pi * radius**2 # volume Vector for Rods; Material weight is considered as constant; Input as Line
                cenl = (element.midpoint.x, element.midpoint.y, element.midpoint.z) # center nodes
                cenl = (cenl[0], cenl[1], 0) # planar Center-nodes
            vol.append(voll)
            cen.append(cenl)


        # Global Equlibrium
        res_pos_x = 0
        res_pos_y = 0

        for i in range(len(e)):
            m_x = cen[i][0] * vol[i]
            m_y = cen[i][1] * vol[i]

            res_pos_x += m_x
            res_pos_y += m_y

            res_pos_x_loc = res_pos_x / sum(vol[:(i+1)]) #moment in x-dir
            res_pos_y_loc = res_pos_y / sum(vol[:(i+1)]) #moment in y-dir

            res_loc = rs.AddLine((res_pos_x_loc, res_pos_y_loc, 0), (res_pos_x_loc, res_pos_y_loc, sum(vol[:(i+1)]))) #Resultant
            se_loc = rg.Brep.IsPointInside(supports[0], rg.Point3d(res_pos_x_loc, res_pos_y_loc, 0), 0.001, False)

            if s_glob == True and allow_temp_support == False:
                if i > s_int+1:
                    allow_temp_support = True

            if se_loc == True: # Structure is in Equilibrium
                static_equilibrium = True
                msg = "Structure is in Equilibrium."

            if se_loc == False and allow_temp_support == False: # Structure is NOT in Equilibrium
                static_equilibrium = False
                msg = "Structure is NOT in Equilibrium."

            if se_loc == False and allow_temp_support == True: # Structure is only in Equilibrium if Robot holds the last Element
                static_equilibrium = True
                allow_temp_support = False
                s_int = i
                msg = "Structure is only in Equilibrium if Robot holds the last Element."

            res = res_loc

    #        if static_equilibrium == False:
    #            break
    #        else:
    #            continue

    #    if res == False:
    #        res = None

        return static_equilibrium, res, msg

    def calculate_local_equilibrium_in_a_branch(self, cp, sp, l, r):
        """
        Calculates the local static Equilibrium condition.

        Parameters
        ----------
        cp : point
            The mid points of the elements.

        Returns
        -------
        la: float
            The lever arm of the branch [m].
        rp: point
            The position of the resultant z-vector [point].

        """

        if cp and sp:
            # Variables:
            # cp = Center Points of the individual elements of one branch
            # sp = Planar Supports of the branch
            # l = #Length of the Rods [m]
            # r = #Radius of the Pipe Elements


            # Step 1: Calculate single Resultants
            vol = l * math.pi * r**2 #Volume Vector for Rods; Material weight is considered as constant
            cp0 = [(p[0], p[1], 0) for p in cp] #Planar Center Points of the Resultant
            sp = [(p[0], p[1], 0) for p in sp] #Make Supports planar


            # Step 2: Calculate the Resultant for each element
            res_pos_x = 0
            res_pos_y = 0

            for i, cp0l in enumerate(cp0):
                m_x = cp0l[0] * vol
                m_y = cp0l[1] * vol

                res_pos_x += m_x # Local Moment in x-dir
                res_pos_y += m_y # Local Moment in y-dir

                res_pos_x_loc = res_pos_x / (vol*(i+1)) # Position of Resultant in x-dir
                res_pos_y_loc = res_pos_y / (vol*(i+1)) # Position of Resultant in y-dir

                rp = rs.AddPoint(res_pos_x_loc, res_pos_y_loc, 0)

                # Lever Arm for a single support
                if len(sp) == 1:
                    la = rs.Distance(rp, sp)

                # Lever Arm for two supports
                if len(sp) == 2:
                    l = rs.AddLine(sp[0], sp[1])
                    la = rs.Distance(rs.EvaluateCurve(l, rs.CurveClosestPoint(l, rp)), rp)

                # Lever Arm for multiple supports
                if len(sp) > 2:
                    sp.append(sp[0])
                    l = rs.AddPolyline(sp)

                    check = rs.PointInPlanarClosedCurve(rp, l)
                    if check == 1 or check == 2: la = 0
                    if check == 0: la = rs.Distance(rs.EvaluateCurve(l, rs.CurveClosestPoint(l, rp)), rp)

        else:
            la = 'No Input'
            rp = 'No Input'

        return([la, rp])

    def calculate_local_equilibrium_in_all_branches(self, current_key, elem_options):

        # Identify the connected elements (branches) in the assembly.
        branches = connected_components(self.network.adjacency)

        stability_feedback = []
        lever_arm_branches = []
        resultant_branches = []

        for i, branch in enumerate(branches):

            # The mid points of the elements in one branch
            cp = [Artist(self.element(bkey).line.midpoint).draw() for bkey in branch]

            # Add option to branch
            if current_key in branch:
                cp += [Artist(elem_options.line.midpoint).draw() for elem_options in elem_options]
            sp = [Artist(self.element(branch[0]).line.end).draw()]

            # calculate local equilibrium (level arm) and the resultant point of the selected option elements
            lever_arm, resultant_point = self.calculate_local_equilibrium_in_a_branch(cp, sp, self.globals['rod_length'], self.globals['rod_radius'])

            resultant_point = rs.coerce3dpoint(resultant_point)
            resultant_line = rg.Line(resultant_point, rg.Vector3d.ZAxis, 0.1)

            lever_arm_branches.append(lever_arm[0])
            resultant_branches.append(resultant_line)

        return lever_arm_branches, resultant_branches

    def close_rf_unit(self,
                      current_key,
                      flip,
                      angle,
                      shift_value,
                      robot_name='AA',
                      robot_AA_base_frame=None,
                      robot_AB_base_frame=None,
                      on_ground=False,
                      frame_measured=None):
        """Add a module to the assembly.
        """

        keys_robot = []

        for i in range(2):
            if i == 0:
                placed_by = 'robot'
                #frame_id = None
                my_new_elem = self.add_rf_unit_element(current_key,
                                                       flip=flip,
                                                       angle=angle,
                                                       shift_value=shift_value,
                                                       placed_by=placed_by,
                                                       robot_name='AA',
                                                       robot_AA_base_frame=robot_AA_base_frame,
                                                       robot_AB_base_frame=robot_AB_base_frame,
                                                       on_ground=False,
                                                       unit_index=i,
                                                       frame_measured=None)
                keys_robot += list(self.network.nodes_where({'element': my_new_elem}))
            else:
                placed_by = 'human'
                #frame_id = added_frame_id
                my_new_elem = self.add_rf_unit_element(current_key,
                                                       flip=flip,
                                                       angle=angle,
                                                       shift_value=shift_value,
                                                       placed_by=placed_by,
                                                       robot_name='AA',
                                                       robot_AA_base_frame=robot_AA_base_frame,
                                                       robot_AB_base_frame=robot_AB_base_frame,
                                                       on_ground=False,
                                                       unit_index=i,
                                                       frame_measured=None)
                keys_human = list((self.network.nodes_where({'element': my_new_elem})))

        keys_dict = {'keys_human': keys_human, 'keys_robot':keys_robot}

        return keys_dict

    def join_branches(self,
                      keys_pair,
                      flip,
                      angle,
                      shift_value,
                      new_elem,
                      robot_name = 'AA',
                      robot_AA_base_frame = None,
                      robot_AB_base_frame = None,
                      on_ground=False,
                      frame_measured=None):
        """Join to branches by adding three elements.
        """

        keys_robot = []

        for i in range(3):
            if i == 0:
                placed_by = 'robot'
                #frame_id = None
                my_new_elem = self.add_rf_unit_element(keys_pair[0],
                                                       flip=flip,
                                                       angle=angle,
                                                       shift_value=shift_value,
                                                       placed_by=placed_by,
                                                       robot_name=robot_name,
                                                       robot_AA_base_frame=robot_AA_base_frame,
                                                       robot_AB_base_frame=robot_AB_base_frame,
                                                       on_ground=False,
                                                       unit_index=i,
                                                       frame_measured=None)
                keys_robot += list(self.network.nodes_where({'element': my_new_elem}))
            if i == 1:
                placed_by = 'human'
                #frame_id = None
                my_new_elem = self.add_rf_unit_element(keys_pair[0],
                                                       flip=flip,
                                                       angle=angle,
                                                       shift_value=shift_value,
                                                       placed_by=placed_by,
                                                       robot_name=robot_name,
                                                       robot_AA_base_frame=robot_AA_base_frame,
                                                       robot_AB_base_frame=robot_AB_base_frame,
                                                       on_ground=False,
                                                       unit_index=i,
                                                       frame_measured=None)
                keys_human = list((self.network.nodes_where({'element': my_new_elem})))
            if i == 2:
                placed_by = 'human'
                #frame_id = None
                my_new_elem = self.add_element(new_elem,
                                               placed_by=placed_by,
                                               robot_name=robot_name,
                                               robot_AA_base_frame=robot_AA_base_frame,
                                               robot_AB_base_frame=robot_AB_base_frame,
                                               on_ground=False,
                                               unit_index=2,
                                               frame_measured=None)
                keys_human = list((self.network.nodes_where({'element': my_new_elem})))

        N = self.network.number_of_nodes()

        d1 = distance_point_point(new_elem.line.end, self.element(keys_pair[1]).frame.point)
        d2 = distance_point_point(new_elem.line.start, self.element(keys_pair[1]).frame.point)

        if d1 < d2:
            self.element(N-1).connector_1_state = False
        else:
            self.element(N-1).connector_2_state = False

        self.element(N-2).connector_1_state = False
        self.element(N-2).connector_2_state = False
        self.element(keys_pair[1]).connector_1_state = False
        self.element(keys_pair[1]).connector_2_state = False

        self.network.add_edge(N-2, N-1, edge_to='neighbour')
        self.network.add_edge(N-2, keys_pair[1], edge_to='neighbour')
        self.network.add_edge(N-1, keys_pair[1], edge_to='neighbour')

        keys_dict = {'keys_human': keys_human, 'keys_robot':keys_robot}

        return keys_dict, d1,d2

    def parent_key(self, point, within_dist):
        """Return the parent key of a tracked object.
        """
        parent_key = None

        for key, element in self.elements():
            connectors = element.connectors(state='open')
            for connector in connectors:
                dist = distance_point_point(point, connector.point)
                if dist < within_dist:
                    parent_key = key

        return parent_key


    def update_connectors_states(self, current_key, flip, my_new_elem, unit_index):


        key_index = self.network.key_index()
        current_elem = self.network.node[current_key]['element']
        keys = [key_index[key] for key in self.network.nodes()]
        previous_elem = self.network.node[keys[-2]]['element']

        if unit_index == 1:
            if current_elem.connector_2_state:
                if flip == 'AA':
                    previous_elem.connector_2_state = False
                    my_new_elem.connector_2_state = False
                if flip == 'AB':
                    previous_elem.connector_2_state = False
                    my_new_elem.connector_1_state = False
                if flip == 'BA':
                    previous_elem.connector_1_state = False
                    my_new_elem.connector_2_state = False
                if flip == 'BB':
                    previous_elem.connector_1_state = False
                    my_new_elem.connector_1_state = False
            if current_elem.connector_1_state:
                if flip == 'AA':
                    previous_elem.connector_1_state = False
                    my_new_elem.connector_1_state = False
                if flip == 'AB':
                    previous_elem.connector_1_state = False
                    my_new_elem.connector_2_state = False
                if flip == 'BA':
                    previous_elem.connector_2_state = False
                    my_new_elem.connector_1_state = False
                if flip == 'BB':
                    previous_elem.connector_2_state = False
                    my_new_elem.connector_2_state = False


    def keys_within_radius(self, current_key):

        for key, element in self.elements(data=True):
            pass

    def keys_within_radius_xy(self, current_key):
        pass

    def keys_within_radius_domain(self, current_key):
        pass

    def range_filter(self, base_frame):
        """Disable connectors outside of a given range, e.g. robot reach.
        """
        ur_range_max = 1.3
        ur_range_min = 0.75

        for key, element in self.elements():
            if element.connector_1_state == True:
                distance = distance_point_point(element.connector_frame_1.point, base_frame.point)
                if not ur_range_min <= distance <= ur_range_max:
                    element.connector_1_state = False
            elif element.connector_2_state == True:
                distance = distance_point_point(element.connector_frame_2.point, base_frame.point)
                if not ur_range_min <= distance <= ur_range_max:
                    element.connector_2_state = False
            else:
                pass

    def distance_to_target_geo(self, key, angle, input_geo):

        open_connector_frame = self.element(key).connectors(state='open')[0]
        elem_frame = self.element(key).frame

        R = Rotation.from_axis_and_angle(elem_frame.xaxis, math.radians(angle), elem_frame.point)

        open_connector_frame_copy = open_connector_frame.transformed(R)
        open_connector_plane = Artist(open_connector_frame_copy).draw()

        closest_point = input_geo.ClosestPoint(open_connector_plane.Origin)
        distance = closest_point.DistanceTo(open_connector_plane.Origin)

        vector = rg.Vector3d(closest_point) - rg.Vector3d(open_connector_plane.Origin)

        return distance, vector

    def orientation_to_target_geo(self, key, angle, input_geo):

        open_connector_frame = self.element(key).connectors(state='open')[0]
        elem_frame = self.element(key).frame

        R = Rotation.from_axis_and_angle(elem_frame.xaxis, math.radians(angle), elem_frame.point)

        open_connector_frame_copy = open_connector_frame.transformed(R)
        open_connector_plane = Artist(open_connector_frame_copy).draw()

        closest_point = input_geo.ClosestPoint(open_connector_plane.Origin)

        vector = Vector(closest_point.X, closest_point.Y, closest_point.Z) - open_connector_frame_copy.point

        #angle = 180 - math.degrees(conn_frame_copy.zaxis.angle(vector))
        v1 = open_connector_frame_copy.zaxis
        v1.unitize()
        vector.unitize()
        dot_product = v1.dot(vector)

        return abs(dot_product)*100, vector

    def all_options_elements(self, flip, angle):
        """Returns a list of elements.
        """
        keys = [key for key, element in self.elements()]
        return [self.element(key).current_option_elements(self, flip, angle) for key in keys]


    def all_options_vectors(self, len):
        """Returns a list of vectors.
        """
        keys = [key for key, element in self.elements()]
        return [self.element(key).current_option_vectors(len) for key in keys]

    def all_options_viz(self, rf_unit_radius):
        """Returns a list of frames.
        """
        keys = [key for key, element in self.elements()]
        return [self.element(key).current_option_viz(rf_unit_radius) for key in keys]


    def connectors(self, state='all'):
        """ Iterate over the connectors of the assembly elements.

        Parameters
        ----------
        state : string
            A string indentifying the connectors' state.

            If 'all', yeild all connectors.
            If 'open' : yeild all open connectors.
            If 'closed' : yeild all closed connectors.

        Yields
        ------
        2-tuple
            The connectors as a (key, frame) tuple.

        """
        for key, element in self.elements():
            if self.element(key).connectors(state):
                yield key, element.connectors(state)

        # keys = [key for key, element in self.elements()]
        # return [(key, self.element(key).connectors(state)) for key in keys]

    def connectors_ranges(self, state='all'):
        """ Iterate over the connectors of the assembly elements.

        Parameters
        ----------
        state : string
            A string indentifying the connectors' state.

            If 'all', yeild all connectors_ranges.
            If 'open' : yeild all open connectors_ranges.
            If 'closed' : yeild all closed connectors_ranges.

        Yieldsframe
        ------
        2-tuple
            The connectors as a (key, cone) tuple.

        """
        for key, element in self.elements():
            yield key, element.connectors_ranges(state)

        # keys = [key for key, element in self.elements()]
        # return [(key, self.element(key).connectors(state)) for key in keys]


    def export_building_plan(self):
        """
        exports the building plan by using the following protocol:

        the first lines are the description of the global markers (fixed in the world frame):
        type [string], element pose [6]
        = "GM", x, y, z, qw, qx, qy, qz

        the next lines contain the wall information:
        type [string], element pose [6], string_message [string]
        = type, x, y, z, qw, qx, qy, qz, string_message
        """

        print("exporting")
        building_plan = []

        for key, element, data in self.elements(data=True):
            line = []

            t = element._type
            line.append(t) #type
            line += element.get_pose_quaternion() #element pose
            string_message = "This is the element with the key index %i" %key
            line.append(string_message)
            building_plan.append(line)

        print(building_plan)
        exporter = Exporter()
        exporter.delete_file()
        exporter.export_building_plan(building_plan)

    def export_to_json_for_xr(self, path, is_built=False):

        self.network.update_default_node_attributes({"is_built":False,"idx_v":None,"custom_attr_1":None,"custom_attr_2":None,"custom_attr_3":None})

        for key, element in self.elements():
            idx_v = self.network.node_attribute(key, "course")
            self.network.node_attribute(key, "idx_v", idx_v)
            self.network.node_attribute(key, "is_built", is_built)

        self.to_json(path)

    def export_to_json_incon(self, path, qr_code, starting_geometry=True, is_built=True, pretty=True):
        buildingplan = {"id":"iaac_plan",'name':"iaac_plan", "description":"iaac_plan", "building_steps":[]}
        building_steps = []
        len = 0

        if starting_geometry:
            element_to_INCON("starting element", len, None, building_steps, True, "starting_material.obj")
            len += 1

        for key, element, data in self.elements(data=True):
            element_to_INCON("dynamic_cylinder", key, element, building_steps, True, "cylinder_for_iaac_workshop.obj")

        placeholder = {"type":"object",'object_type':"cylinder_for_iaac_workshop_1m.obj", "id": "dynamic_cylinder", "is_tag": False, "is_already_built": False, "color_rgb": [1.0, 0.0, 0.0],"instances": 200,"build_instructions" : []}
        building_steps.append(placeholder)

        for key, tag in enumerate(qr_code):
            tag_to_INCON(key, tag, building_steps)

        buildingplan['building_steps'] = building_steps
        compas.json_dump(buildingplan, path, pretty)


    def assembly_to_json(self, path, pretty):

        building_plan = {"node":{}}

        for key, element, data in self.elements(data=True):
            elem_dict = {}
            elem_dict["element"] = {"frame" : self.element(key).frame.to_data()}

            elem_dict["is_planned"] = data["is_planned"],
            elem_dict["is_built"] = data['is_built'],
            elem_dict["placed_by"] = data["placed_by"],
            elem_dict["is_support"] = data["is_support"],
            elem_dict["is_held_by_robot"] = data["is_held_by_robot"],
            elem_dict["robot_frame"] = data["robot_frame"],
            elem_dict["frame_measured"] = data["frame_measured"]

            building_plan["node"][str(key)] = elem_dict

        compas.json_dump(building_plan, path, pretty)
