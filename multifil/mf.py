#!/usr/bin/env python
# encoding: utf-8
"""
mf.py - A myosin thick filament

Created by Dave Williams on 2010-01-04.
"""

from . import mh
from . import ti
import numpy as np


class Crown:
    """Three cross-bridges on a thick filament at a given axial location

    Crowns are a physiologically relevant division of the thick filament.
    They are clusters of three cross-bridges that hang off of the thick
    filament, separated from each other by a 120 degree rotation about the
    thick filament's pitch. In this model, they serve as force distribution
    nodes; any axial or radial force that a crown's cross-bridge generates
    is felt equally by the other two cross-bridges.
    """
    def __init__(self, parent_thick, index, cross_bridges, orientations):
        """Create the myosin crown

        Parameters:
            parent_thick: the calling thick filament instance
            index: the axial index on the parent thick filament
            cross_bridges: the cross-bridges that populate the crown
            orientations: select between two crown orientations (0 or 1)
        """
        # Remember the passed attributes
        self.parent_thick = parent_thick
        self.index = index
        self.crossbridges = cross_bridges
        # Remember how I can find you
        self.address = ('crown', self.parent_thick.index, self.index)
        # Use the passed orientation (type 0 or 1) to create the orientation
        # vectors that the crown uses to pass back proper radial forces
        # NB: vectors are ((face_0,face_2, face_3), (face_1, face_3, face_5))
        crown_vectors = (((-0.886, 0.5), (0.866, 0.5), (0, -1)),
                ((0, 1), (0.866, -0.5), (-0.866, -0.5)))
        self.orientations = crown_vectors[orientations]

    def to_dict(self):
        """Create a JSON compatible representation of the crown

        Example usage: json.dumps(crown.to_dict(), indent=1)

        Current output includes:
            address: largest to most local, indices for finding this
            crossbridges: addresses of attached xbs
            orientations: vectors used to pass back radial forces
        """
        crownd = self.__dict__.copy()
        crownd.pop('index')
        crownd.pop('parent_thick')
        crownd['crossbridges'] = [xb.address for xb in crownd['crossbridges']]
        return crownd

    def from_dict(self, cd):
        """ Load values from a crown dict. Values read in correspond
        to the current output documented in to_dict.
        """
        # Check for index mismatch
        read, current = tuple(cd['address']), self.address
        assert read==current, "index mismatch at %s/%s"%(read, current)
        # Local keys
        self.orientations = cd['orientations']
        # Remote keys
        self.crossbridges = [self.parent_thick.resolve_address(xba) \
                             for xba in cd['crossbridges']]

    def axialforce(self, axial_location=None):
        """The sum of the axial force generated by each head"""
        axial_force = [xb.axialforce(axial_location) for
                xb in self.crossbridges]
        return sum(axial_force)

    def radialforce(self):
        """Radial the sum of force generated by each head as a vector (y,z)"""
        radial_forces = []
        for crossbridge, orient in zip(self.crossbridges, self.orientations):
            force_mag = crossbridge.radialforce()
            radial_forces.append(np.multiply(force_mag, orient))
        return np.sum(radial_forces, 0)

    def transition(self):
        """Put each head through a transition cycle """
        transitions = [xb.transition() for xb in self.crossbridges]
        return transitions

    @property
    def lattice_spacing(self):
        """Do what it says on the tin"""
        return self.parent_thick.lattice_spacing

    @property
    def axial_location(self):
        """Do what it says on the tin, return this crown's axial location"""
        return self.parent_thick.get_axial_location(self.index)


class ThickFace:
    """Represent one face of a thick filament

    Thick filaments have six faces, arranged thus:
     ----------------------
     | Myosin face order  |
     |--------------------|
     |         a1         |
     |     a0      a2     |  ^
     |         mf         |  |
     |     a5      a3     |  Z
     |         a4         |   Y-->
     ----------------------
    Because myosin crowns are arranged in the following pattern, faces will
    either have one cross-bridge ever 42.9nm or a repeating pattern wherein
    each set has a cross-bridge, a gap of 28.6 nm, a cross-bridge, and a
    final gap of 14.3 nm before the pattern repeats.
    ----------------------------------------------------
    | Crown Level 1  | Crown Level 2  | Crown Level 3  |
    |  0nm offset    | 14.3 nm later  | 14.3 nm later  |
    |----------------|----------------|----------------|
    |       a1       |       a1       |       a1       |
    |    a0    a2    |    a0 |  a2    |    a0    a2    |
    |      \M1/     -->     /M1\     -->     \M1/      |
    |    a5 |  a3    |    a5    a3    |    a5 |  a3    |
    |       a4       |       a4       |       a4       |
    ----------------------------------------------------
    Further discussion is located in the "ThickFilament" documentation.
    """
    def __init__(self, parent_filament, axial_locations, thin_face,
            index, start):
        """Instantiate the thick filament face with its heads

        Parameters:
            parent_filament: the thick filament supporting this face
            axial_locations: the axial locations of nodes along the face,
                we want this list kept linked to the filament's version
            thin_face: the thin filament face located opposite
            index: the numerical orientation index of this face (0-5)
            start: what crown level this face starts on (1, 2, or 3)
        """
        # Remember the calling parameters
        self.parent_filament = parent_filament
        self.thin_face = thin_face
        self.index = index # numerical orientation (0-5)
        self.address = ('thick_face', self.parent_filament.index, self.index)
        self.axial_locations = axial_locations
        # Instantiate the cross-bridges along the face
        self.xb = []
        self.xb_by_crown = [] # Includes levels with no heads
        crown_level = start
        # For faces in positions 0, 2, or 4 ...
        if index in (0, 2, 4):
            # look at each thick filament crown location ...
            for i in range(len(axial_locations)):
                # and add cross-bridges at the appropriate locations.
                if crown_level in (1, 3):
                    head = mh.Crossbridge(i, self, thin_face)
                    self.xb.append(head)
                    self.xb_by_crown.append(head)
                elif crown_level == 2:
                    self.xb_by_crown.append(None)
                # Increment the crown level, cycling back to 1 after 3.
                crown_level = crown_level % 3 + 1
        elif index in (1, 3, 5):
            for i in range(len(axial_locations)):
                if crown_level in (1, 3):
                    self.xb_by_crown.append(None)
                elif crown_level == 2:
                    head = mh.Crossbridge(i, self, thin_face)
                    self.xb.append(head)
                    self.xb_by_crown.append(head)
                crown_level = crown_level % 3 + 1
        # Record the thick filament node index at which cross-bridge sits
        self.xb_index = [xb.index for xb in self.xb]

    def __str__(self):
        """The string representation of the thick filament face
        The representation is as follows:
            Thick -    |====================
            Bindings -   |  |   |  |  \ \
            Bindings         | |  | |   \   \
            Thin -       ------------------------------|
            Where | is a loosely bound XB and \ is strongly bound
        """
        thick = '|' + len(self.xb) * '='
        xb_string = [' ', '|', '\\']
        thickbnd = ' ' + ''.join([xb_string[xb.numeric_state]
                                  for xb in self.xb])
        thinbnd = 12*' ' + ''.join([xb_string[act.state]
                                for act in self.thin_face.binding_sites])
        thin = 12*' ' + len(self.thin_face.binding_sites) * '-' + '|'
        return (thick + '\n' + thickbnd + '\n' + thinbnd + '\n' + thin + '\n')

    def to_dict(self):
        """Create a JSON compatible representation of the thick face

        Example usage: json.dumps(thickface.to_dict(), indent=1)

        Current output includes:
            address: largest to most local, indices for finding this
            thin_face: the opposing thin face
            xb: a list of the cross-bridges on this face
            xb_by_crown: a list of the address of cross-bridges sorted by crown
            xb_index: thick filament node index at which each cross-bridge sits
            axial_locations: the locations of each node along the face
        """
        thickfaced = self.__dict__.copy()
        thickfaced.pop('index')
        thickfaced.pop('parent_filament')
        thickfaced['thin_face'] = thickfaced['thin_face'].address
        thickfaced['titin_fil'] = thickfaced['titin_fil'].address
        thickfaced['xb'] = [xb.to_dict() for xb in thickfaced['xb']]
        thickfaced['xb_by_crown'] = [xb.address if xb is not None else None\
                                     for xb in thickfaced['xb_by_crown']]
        return thickfaced

    def link_titin(self, titin_fil):
        """Add a titin filament to this face"""
        self.titin_fil = titin_fil

    def from_dict(self, tfd):
        """ Load values from a thick face dict. Values read in correspond
        to the current output documented in to_dict.
        """
        # Check for index mismatch
        read, current = tuple(tfd['address']), self.address
        assert read==current, "index mismatch at %s/%s"%(read, current)
        # Local keys
        self.axial_locations = tfd['axial_locations']
        self.xb_index = tfd['xb_index']
        # Sub-structure and remote keys
        self.thin_face = self.parent_filament.parent_lattice.resolve_address(
            tfd['thin_face'])
        self.titin_fil = self.parent_filament.parent_lattice.resolve_address(
            tfd['titin_fil'])
        self.xb_by_crown = [self.resolve_address(xba) if xba is not None \
                            else None for xba in tfd['xb_by_crown']]
        for data, xb in zip(tfd['xb'], self.xb):
            xb.from_dict(data)

    def resolve_address(self, address):
        """Give back a link to the object specified in the address
        We should only see addresses starting with 'xb'
        """
        if address[0] == 'xb':
            return self.xb_by_crown[address[3]]
        import warnings
        warnings.warn("Unresolvable address: %s"%str(address))

    def axialforce(self):
        """Return the total axial force of the face's cross-bridges"""
        axial = [crossbridge.axialforce() for crossbridge in self.xb]
        return sum(axial)

    def radialtension(self):
        """Sum of the absolute values of radial force for every myosin"""
        radial = [crossbridge.radialforce() for crossbridge in self.xb]
        radial.append(self.titin_fil.radialforce())
        return sum(radial)

    def radialforce(self):
        """The radial force this face experiences

        Parameters:
            None:
        Returns:
            radial_force: sum of radial force of each myosin along the face
        """
        radial = [crossbridge.radialforce() for crossbridge in self.xb]
        return sum(radial)

    def transition(self):
        """Give each of the face's cross-bridges a chance to transition"""
        transitions = [crossbridge.transition() for crossbridge in self.xb]
        return transitions

    def get_xb(self, crossbridge_index = None):
        """Return an XB of interest or a list of all the face's XBs"""
        if crossbridge_index is None:
            return self.xb
        else:
            return self.xb_by_crown[crossbridge_index]

    def get_axial_location(self, crossbridge_index):
        """Return the axial location of a cross-bridge"""
        return self.parent_filament.get_axial_location(crossbridge_index)

    def get_states(self):
        """Return the numeric states (0,1,2) of all cross-bridges"""
        return [xb.numeric_state for xb in self.xb]

    @property
    def lattice_spacing(self):
        """Return lattice spacing to the face's opposite number"""
        return self.parent_filament.lattice_spacing


class ThickFilament:
    """The thick filament is a string of myosin crowns

    It is attached to the m-line at one end and to nothing
    at the other (yet).
    """
    def __init__(self, parent_lattice, index, thin_faces, start, k=None):
        """Initialize the thick filament.

        Parameters:
            parent_lattice: the calling half-sarcomere instance
            index: which thick filament you are
            thin_faces: links to six surrounding actin filament faces
            start: initial crown level (1-3)

        ## Actin filament arrangement
        The actin filament list should be as follows:

                a1        ^
            a0      a2    |   ^
                mf        z  /
            a5      a3      x
                a4           y-->

        ## Crown orientations
        The rotation of neighboring crowns is different than that used in
        existing spatially explicit models, and is taken from new analysis
        of mammalian cardiac muscle.  Thick filaments sprout myosin crowns
        every 14.3nm, with a repeating pattern of azimuthal perturbation
        (rotation around the thick filament's long axis) every three crown
        lengths [(1)][AlKhayat2008].  The azimuthal perturbation is such
        that the first and third crowns in any 43nm repeat are rotated by
        60 degrees from the second crown's orientation [(1)][AlKhayat2008].

        This relates to the nearby actin filaments such that the crowns
        come in two configurations, linked to either actin filaments 0, 2,
        and 4 or 1, 3, and 5. They are arranged in an "A, B, A, A, B, A,
        ..." repeating pattern.

        ## Crown spacing and thick filament length
        Omitting the bare zone, the crown-decorated region of a half thick-
        filament is 858 nm long and consists of 60 myosin nodes and one node 
        at the M-line [(2)][Tanner2007].  As each of the myosin nodes is a 
        3-myosin crown, each half-thick filament will have 180 myosins, 
        slightly more than the 150 present in mammalian striated muscle 
        [(2)][Tanner2007].  The M-line side of the thick filament has an 
        initial bare zone of from 80 nm [(3)][Higuchi1995] to 58 nm 
        [(2)][Tanner2007]. We choose to use the 58nm value.

        The crowns are on a 43 nm repeat, with three crowns per repeat.
        This means that each crown will be spaced 43/3 = 14.3 nm apart.

        ## Orientation and parsing into faces

        The thick filament is also organized into faces, collections
        of cross-bridges that are opposite opposing acting faces. These
        six faces provide another way to organize the thick filament,
        one from which it is more easy to group all the interactions
        that occur between the thick filament and one of its adjacent
        thin filaments. The main drawback of these faces is that they
        are subject to irregular cross-bridge distributions as a result
        of what "crown level" the thick filament starts on and as a result
        of the fact that three of the adjacent thin filaments get more
        opportunities to interact with the thick filament than do the
        other three thin filaments (see the documentation of the thick
        filament faces for more information). The cross-bridge patterns
        of the thick filament faces with various initial conditions
        are shown below.

        ### Opposite actin faces 0, 2, and 4
        ||==========================================================||
        ||      Start at crown level 1                              ||
        || M    |----|---|---|---|---|---|---|---|---|-... <--Nodes ||
        || Line |    \       \   \       \   \       \     <--XBs   ||
        ||==========================================================||
        ||      Start at crown level 2                              ||
        || M    |----|---|---|---|---|---|---|---|---|-... <--Nodes ||
        || Line |        \   \       \   \       \   \     <--XBs   ||
        ||==========================================================||
        ||      Start at crown level 3                              ||
        || M    |----|---|---|---|---|---|---|---|---|-... <--Nodes ||
        || Line |    \   \       \   \       \   \         <--XBs   ||
        ||==========================================================||

        ### Opposite actin faces 1, 3, and 5
        ||==========================================================||
        ||      Start at crown level 1                              ||
        || M    |----|---|---|---|---|---|---|---|---|-... <--Nodes ||
        || Line |        \           \           \         <--XBs   ||
        ||==========================================================||
        ||      Start at crown level 2                              ||
        || M    |----|---|---|---|---|---|---|---|---|-... <--Nodes ||
        || Line |    \           \           \             <--XBs   ||
        ||==========================================================||
        ||      Start at crown level 3                              ||
        || M    |----|---|---|---|---|---|---|---|---|-... <--Nodes ||
        || Line |            \           \           \     <--XBs   ||
        ||==========================================================||

        ## Other parameters
        The spring constant of the thick filament, the sections connecting
        myosin crowns, is 2020 pN/nm [(4)][Daniel1998].

        [AlKhayat2008]:http://dx.doi.org/10.1016/j.jsb.2008.03.011
        [Tanner2007]:http://dx.doi.org/10.1371/journal.pcbi.0030115
        [Higuchi1995]:http://www.ncbi.nlm.nih.gov/pmc/articles/PMC1236329
        [Daniel1998]:http://dx.doi.org/10.1016/S0006-3495(98)77875-0
        """
        # Remember who created you
        self.parent_lattice = parent_lattice
        # Remember who you are
        self.index = index
        self.address = ('thick_fil', index)
        # Create a list of crown axial locations and relevant data
        bare_zone = 58 # Length of the area before any crowns, nm
        crown_spacing = 14.3 # Spacing between adjacent crowns, nm
        n_cr = 60 # Number of myosin crowns
        self.axial = [bare_zone + n*crown_spacing for n in range(n_cr)]
        self.rests = np.diff(np.hstack([0, self.axial]))
        # Instantiate the faces
        self.thick_faces = []
        for face_index in range(len(thin_faces)):
            self.thick_faces.append(ThickFace(self, self.axial,
                thin_faces[face_index], face_index, start))
        # Find the crown levels (1, 2, or 3) and orientation vectors
        crown_levels = [(n+start-1)%3+1 for n in range(n_cr)]
        crown_orientations = [0 + (l == 2) for l in crown_levels]
        # Instantiate the myosin crowns
        self.crowns = []
        # For each crown position...
        for index in range(n_cr):
            crown_xbs = []
            # look at the cross-bridges for each face...
            for face in self.thick_faces:
                current_xb = face.get_xb(index)
                # and store it and its face if the cross-bridge exists.
                if current_xb is not None:
                    crown_xbs.append(current_xb)
            # Create a crown with these faces and cross-bridges.
            self.crowns.append(Crown(self, index, crown_xbs,
                crown_orientations[index]))
        # Thick filament properties to remember
        self.number_of_crowns = n_cr
        self.thin_faces = thin_faces
        if k is None:
            k = 2020 # Spring constant of thick filament in pN/nm
        self.k = k
        self.b_z = bare_zone

    def __str__(self):
        """String representation of the thick filament"""
        faces = '' .join(["Face " + str(face.index) + ": \n" +
                    face.__str__() + '\n'
                    for face in self.thick_faces])
        return faces

    def to_dict(self):
        """Create a JSON compatible representation of the thick filament

        Example usage: json.dumps(thick.to_dict(), indent=1)

        Current output includes:
            address: largest to most local, indices for finding this
            axial: axial locations of the nodes along the thick fil
            b_z: length of this half of the central bare zone
            crowns: dicts of the crowns
            k: thick filament stiffness
            number_of_crowns: number of crowns
            rests: the rest distances between the axial nodes
            thick_faces: dicts of the thick faces
            thin_faces: addresses of the opposing thin faces
        """
        thickd = self.__dict__.copy()
        thickd.pop('index')
        thickd.pop('parent_lattice')
        thickd['axial'] = list(thickd['axial'])
        thickd['crowns'] = [crown.to_dict() for crown in thickd['crowns']]
        thickd['rests'] = list(thickd['rests'])
        thickd['thick_faces'] = [face.to_dict() for face in\
                                 thickd['thick_faces']]
        thickd['thin_faces'] = [face.address for face in thickd['thin_faces']]
        return thickd

    def from_dict(self, td):
        """ Load values from a thick filament dict. Values read in correspond
        to the current output documented in to_dict.
        """
        # Check for index mismatch
        read, current = tuple(td['address']), self.address
        assert read==current, "index mismatch at %s/%s"%(read, current)
        # Check for crown number mismatch
        read, current = td['number_of_crowns'], self.number_of_crowns
        assert read==current, "crown number mismatch of %s/%s"%(read, current)
        # Local keys
        self.axial = np.array(td['axial'])
        self.rests = np.array(td['rests'])
        self.k = td['k']
        self.b_z = td['b_z']
        # Sub-structure and remote keys
        self.thin_faces = tuple([self.parent_lattice.resolve_address(tfa)
                                 for tfa in td['thin_faces']])
        for data, crown in zip(td['crowns'], self.crowns):
            crown.from_dict(data)
        for data, face in zip(td['thick_faces'], self.thick_faces):
            face.from_dict(data)

    def resolve_address(self, address):
        """Give back a link to the object specified in the address
        We should only see addresses starting with 'thick_face', 'crown',
        or 'xb'
        """
        if address[0] == 'crown':
            return self.crowns[address[2]]
        elif address[0] == 'thick_face':
            return self.thick_faces[address[2]]
        elif address[0] == 'xb':
            return self.thick_faces[address[2]].resolve_address(address)
        import warnings
        warnings.warn("Unresolvable address: %s"%str(address))

    def effective_axial_force(self):
        """Get the axial force generated at the M-line

        This looks only at the force due to the crown next to the
        M-line, as this is the only point on the thick filament that
        can /directly/ generate force upon the M-line. It does not
        account for internal strain along the other nodes or force due
        to bound cross-bridges.
        It is assumed that the M-line is at an x location of 0.
        Return:
            force: the axial force at the M-line
        """
        return (self.axial[0] - self.b_z) * self.k

    def axial_force_of_each_crown(self, axial_locations=None):
        """Return the total cross-bridge force on each crown
        This does not take into account the force from thick filament springs
        """
        if axial_locations == None:
            axial_force = [cr.axialforce() for cr in self.crowns]
        else:
            axial_force = [cr.axialforce(loc) for
                    cr,loc in zip(self.crowns, axial_locations)]
        return axial_force

    def axialforce(self, axial_locations=None):
        """Return a list of axial forces at each crown location

        This returns the force at each crown, accounting for the
        internal strain of the thick filament and the force generated
        by bound cross-bridge heads.
        Parameters:
            axial_locations: location of each crown (optional)
        Return:
            force: the sum of the axial forces generated by all crowns
        """
        # Calculate the force exerted by the thick filament's backbone
        thick = self._axial_thick_filament_forces(axial_locations)
        # Retrieve the force each crown generates
        crown = self.axial_force_of_each_crown(axial_locations)
        # Return the combination of backbone and crown forces
        return np.add(thick, crown)

    def settle(self, factor):
        """Reduce the total axial force on the system by moving the crowns"""
        # Total axial force on each point
        forces = self.axialforce()
        # Individual displacements needed to balance force
        isolated = factor*forces/self.k
        isolated[-1] *= 2 # Last node has spring on only one side
        # Cumulative displacements
        cumulative = np.cumsum(isolated)
        # New axial locations
        self.axial += cumulative
        return forces

    def radialtension(self):
        """The radial tension this filament experiences

        Parameters:
            None
        Returns:
            radial_tension: the sum of the absolute value of the radial
                force that each cross-bridge along the filament experiences
        """
        face_tensions = [face.radialtension() for face in self.thick_faces]
        return sum(face_tensions)

    def radial_force_of_each_crown(self):
        """Return a list of the radial force vectors (y,z) of each crown"""
        radial_forces = [cr.radialforce() for cr in self.crowns]
        return radial_forces

    def radial_force_of_filament(self):
        """Gives the radial force generate by the entire filament

        Parameters:
            None
        Return:
            radial_force: (y,z) vector of radial force from all crowns"""
        # Retrieve the force all crowns generate
        crown_forces = self.radial_force_of_each_crown()
        # Return the combination of all crown forces
        return np.sum(crown_forces, 0)

    def displacement_per_crown(self):
        """How far each crown/node has moved from it's rest position"""
        dists = np.diff(np.hstack([0, self.axial]))
        return dists - self.rests

    def displacement(self):
        """Total offset of all nodes from their rest positions"""
        return np.sum(np.abs(self.displacement_per_crown()))

    def transition(self):
        """Give each cross-bridge in the filament a chance to transition"""
        transitions = [crown.transition() for crown in self.crowns]
        return transitions

    def get_axial_location(self, index):
        """Return the axial location at the given crown index"""
        return self.axial[index]

    def get_states(self):
        """Return the numeric states (0,1,2) of each face's cross-bridges"""
        return [face.get_states() for face in self.thick_faces]

    @property
    def lattice_spacing(self):
        """Return the lattice's spacing"""
        return self.parent_lattice.lattice_spacing

    def _axial_thick_filament_forces(self, axial_locations=None):
        """The axial force generated by the thick filament at each crown

        This returns the axial force at each thick filament location,
        not counting any force generated by bound cross-bridge heads.
        Parameters:
            axial_locations: location of each crown (optional)
        Return:
            forces: axial force of the thick filament at each crown
        """
        # Use the thick filament's stored axial locations if none are passed
        if axial_locations == None:
            axial_locations = np.hstack([0, self.axial])
        else:
            axial_locations = np.hstack([0, axial_locations])
        # Find the distance from crown to crown, then the resulting forces
        dists = np.diff(axial_locations)
        spring_force = (dists - self.rests) * self.k
        # Location zero is the force of titin
        net_force_at_crown = np.diff(spring_force)
        titin_force = self._normed_total_titin_force()
        spring_force = np.hstack([spring_force, titin_force])
        net_force_at_crown = np.diff(spring_force)
        return net_force_at_crown

    def _normed_total_titin_force(self):
        """Settle expects to move nodes to satisfy springs of stiffness self.k.
        Titin has a different stiffness. We express the force titin is
        generating in terms of the thick fil stiffness in order to treat the
        movement necessary to balance the node attached to titin the same as
        the movement necessary to balance the force of the thick filaments.
        """
        normed_titin_forces = []
        for thick_face in self.thick_faces:
            titin = thick_face.titin_fil
            titin_force = titin.axialforce()
            normed = titin_force * titin.stiffness() / self.k
            normed_titin_forces.append(normed)
        return np.sum(normed_titin_forces)

    @staticmethod
    def _radial_force_to_components(crown_force, orientation):
        """Convert radial components of a crown's force into a y,z vector

        Myosin crowns come in two varieties, types a and b. They are
        oriented thusly:
            Type A          Type B
          a0      a1          a0
              mf
                              mf
              a2          a2      a1
        The purpose of this function is to sort the force a single crown
        generates out into a single (y,z) vector.
        Parameters:
            crown_force: force a single crown generates, (f_a0, f_a1, f_a2)
            orientation: that crown's orientation; 0 for type A, 1 for B
        Returns:
            force: the force the crown generates, (y, z)
        """
        if orientation == 0:
            f_y = -0.866 * crown_force[0] + 0.866 * crown_force[1]
            f_z = 0.5 * crown_force[0] + 0.5 * crown_force[1] - crown_force[2]
        else:
            f_y = 0.866 * crown_force[1] - 0.866 * crown_force[2]
            f_z = crown_force[0] - 0.5 * crown_force[1] - 0.5 * crown_force[2]
        return (f_y, f_z)


if __name__ == '__main__':
    print("mf.py is really meant to be called as a supporting module")
