#!/usr/bin/env python
# encoding: utf-8
"""
mf.py - A myosin thick filament

Created by Dave Williams on 2010-01-04.
"""

import mh
import numpy as np


class Crown(object):
    """Three cross-bridges on a thick filament at a given axial location
    
    Crowns are a physiologically relevant division of the thick filament. 
    They are clusters of three cross-bridges that hang off of the thick 
    filament, separated from each other by a 120 degree rotation about the 
    thick filament's pitch. In this model, they serve as force distribution 
    nodes; any axial or radial force that a crown's cross-bridge generates 
    is felt equally by the other two cross-bridges.
    """
    def __init__(self, parent_thick, thick_index, 
            cross_bridges, orientations):
        """Create the myosin crown
        
        Parameters:
            parent_thick: the calling thick filament instance
            thick_index: the axial index on the parent thick filament
            cross_bridges: the cross-bridges that populate the crown
            orientations: select between two crown orientations (0 or 1)
        """
        # Remember the passed attributes
        self.parent_thick = parent_thick
        self.thick_index = thick_index
        self.crossbridges = cross_bridges
        # Use the passed orientation (type 0 or 1) to create the orientation
        # vectors that the crown uses to pass back proper radial forces
        # NB: vectors are ((face_0,face_2, face_3), (face_1, face_3, face_5))
        crown_vectors = (((-0.886, 0.5), (0.866, 0.5), (0, -1)), 
                ((0, 1), (0.866, -0.5), (-0.866, -0.5)))
        self.orientations = crown_vectors[orientations]
    
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
    
    def get_lattice_spacing(self):
        """Do what it says on the tin"""
        return self.parent_thick.get_lattice_spacing()
    
    def _set_timestep(self, timestep):
        """Set the length of time step used to calculate transitions"""
        [xb._set_timestep(timestep) for xb in self.crossbridges]
    
    def get_axial_location(self):
        """Do what it says on the tin, return this crown's axial location"""
        return self.parent_thick.get_axial_location(self.thick_index)


class ThickFace(object):
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
            orientation, start):
        """Instantiate the thick filament face with its heads
        
        Parameters:
            parent_filament: the thick filament supporting this face
            axial_locations: the axial locations of nodes along the face,
                we want this list kept linked to the filament's version
            thin_face: the thin filament face located opposite 
            orientation: the numerical orientation of this face (0-5) 
            start: what crown level this face starts on (1, 2, or 3)
        """
        # Remember the calling parameters
        self.parent_filament = parent_filament 
        self.axial_locations = axial_locations
        self.thin_face = thin_face
        self.orientation = orientation # numerical orientation (0-5)
        # Instantiate the cross-bridges along the face
        self.xb = []
        self.xb_by_crown = [] # Includes levels with no heads
        crown_level = start
        # For faces in positions 0, 2, or 4 ...
        if orientation in (0, 2, 4):
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
        elif orientation in (1, 3, 5):
            for i in range(len(axial_locations)):
                if crown_level in (1, 3):
                    self.xb_by_crown.append(None)
                elif crown_level == 2:
                    head = mh.Crossbridge(i, self, thin_face)
                    self.xb.append(head)
                    self.xb_by_crown.append(head)
                crown_level = crown_level % 3 + 1 
        # Record the thick filament node index at which cross-bridge sits
        self.xb_index = [xb.face_index for xb in self.xb]
    
    def __repr__(self):
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
        thickbnd = ' ' + ''.join([xb_string[xb.get_numeric_state()] 
                                  for xb in self.xb])
        thinbnd = 12*' ' + ''.join([xb_string[act.get_state()]
                                for act in self.thin_face.binding_sites])
        thin = 12*' ' + len(self.thin_face.binding_sites) * '-' + '|'
        return (thick + '\n' + thickbnd + '\n' + thinbnd + '\n' + thin + '\n')
    
    def axialforce(self):
        """Return the total axial force of the face's cross-bridges"""
        axial = [crossbridge.axialforce() for crossbridge in self.xb]
        return sum(axial)
    
    def radialtension(self):
        """Sum of the absolute values of radial force for every myosin"""
        radial = [crossbridge.radialforce() for crossbridge in self.xb]
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
        return self.parent_filament.axial[crossbridge_index]
    
    def get_states(self):
        """Return the numeric states (0,1,2) of all cross-bridges"""
        return [xb.get_numeric_state() for xb in self.xb]
      
    def get_lattice_spacing(self):
        """Return lattice spacing to the face's opposite number"""
        return self.parent_filament.get_lattice_spacing() 


class ThickFilament(object):
    """The thick filament is a string of myosin crowns
    
    It is attached to the m-line at one end and to nothing 
    at the other (yet).
    """
    def __init__(self, parent_lattice, thin_faces, start):
        """Initialize the thick filament. 
        
        Parameters:
            parent_lattice: the calling half-sarcomere instance
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
        Each half thick filament is 858 nm long and consists of 60 myosin 
        nodes and one node at the M-line [(2)][Tanner2007].  As each of the 
        myosin nodes is the location of a 3-myosin crown, each half-thick 
        filament will have 180 myosins, slightly more than the 150 present 
        in mammalian striated muscle [(2)][Tanner2007].  The M-line side of 
        the thick filament has an initial bare zone of from 80 nm
        [(3)][Higuchi1995] to 58 nm [(2)][Tanner2007]. 
        
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
        # Create a list of crown axial locations and relevant data
        bare_zone = 58 # Length of the area before any crowns
        crown_spacing = 14.3 # Spacing between adjacent crowns
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
        self.k = 2020 # Spring constant of thick filament in pN/nm
        self.b_z = bare_zone
    
    def __repr__(self):
        """String representation of the thick filament"""
        faces = '' .join(["Face " + str(face.orientation) + ": \n" +
                    face.__repr__() + '\n'
                    for face in self.thick_faces])
        return faces
    
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
        """Return a list of the axial force on each crown"""
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
    
    def stress(self):
        """A metric for how offset the nodes are from rest positions
        
        How good of a metric this is remains to be seen. It is just the
        total displacement of all crowns from their axial rest positions.
        """
        dists = np.diff(np.hstack([0, self.axial]))
        return np.sum(np.abs(dists - self.rests))
    
    def transition(self):
        """Give each cross-bridge in the filament a chance to transition"""
        transitions = [crown.transition() for crown in self.crowns]
        return transitions
    
    def get_axial_location(self, index):
        """Return the axial location at the given crown index"""
        return self.axial[index]
    
    def _set_timestep(self, timestep):
        """Set the length of time step used to calculate transitions"""
        [crown._set_timestep(timestep) for crown in self.crowns]
    
    def get_states(self):
        """Return the numeric states (0,1,2) of each face's cross-bridges"""
        return [face.get_states() for face in self.thick_faces]
    
    def get_lattice_spacing(self):
        """Return the lattice's spacing"""
        return self.parent_lattice.get_lattice_spacing()
    
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
        spring_force = np.hstack([spring_force, 0]) # Last node not connected
        net_force_at_crown = np.diff(spring_force) 
        return net_force_at_crown
    
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