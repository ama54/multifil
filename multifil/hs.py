#!/usr/bin/env python
# encoding: utf-8
"""
hs.py - A half-sarcomere model with multiple thick and thin filaments

Created by Dave Williams on 2009-12-31.
"""

import sys
import multiprocessing as mp
import time
import numpy as np

from multifil import af
from multifil import mf


class hs:
    """The half-sarcomere and ways to manage it"""

    def __init__(self, lattice_spacing=None, z_line=None, poisson=None,
                 actin_permissiveness=None, timestep_len=1,
                 time_dependence=None, starts=None):
        """ Create the data structure that is the half-sarcomere model

        Parameters:
            lattice_spacing: the surface-to-surface distance (14.0)
            z_line: the length of the half-sarcomere (1250)
            poisson: poisson ratio obeyed when z-line changes. Significant
                values are:
                    * 0.5 - constant volume
                    * 0.0 - constant lattice spacing, default value
                    * any negative value - auxetic lattice spacing
            actin_permissiveness: how open actin sites are to binding (1.0)
            timestep_len: how many ms per timestep (1)
            time_dependence: a dictionary to override the initial lattice
                spacing, sarcomere length, and actin permissiveness at each
                timestep. Each key may contain a list of the values, to be
                iterated over as timesteps proceed. The first entry in these
                lists will override passed initial values. The valid keys
                time_dependence can control are:
                    * "lattice_spacing"
                    * "z_line"
                    * "actin_permissiveness"
            starts: starting polymer/orientation for thin/thick filaments in
                form ((rand(0,25), ...), (rand(0,3), ...))
        Returns:
            None

        This is the organizational basis that the rest of the model, and
        classes representing the other structures therein will use when
        running. It contains the following properties:

        ## Half-sarcomere properties: these are properties that can be
        interpreted as belonging to the overall model, not to any thick or
        thin filament.

        lattice_spacing:
            the face to face lattice spacing for the whole model
        m_line:
            x axis location of the m line
        h_line:
            x axis location of the h line
        hiding_line:
            x axis location below which actin sites are hidden by actin
            overlap (crossing through the m-line from adjacent half sarc)

        ## Thick Filament Properties: each is a tuple of thick filaments
        (filament_0, filament_1, filament_2, filament_3) where each
        filament_x is giving the actual properties of that particular
        filament.

        thick_location:
            each tuple location is a list of x axis locations
        thick_crowns:
            each tuple location is a tuple of links to crown instances
        thick_link:
            each tuple location is a list consisting of three (one for each
            myosin head in the crown) of either None or a link to a thin_site
        thick_adjacent:
            each tuple location is a tuple of links to adjacent thin filaments
        thick_face:
            each tuple location is a tuple of length six, each location of
            which contains a tuple of links to myosin heads that are facing
            each surrounding thin filament
        thick_bare_zone:
            a single value, the length of each filament before the first crown
        thick_crown_spacing:
            a single value, the distance between two crowns on a single filament
        thick_k:
            a single value, the spring constant of the thick filament between
            any given pair of crowns

        ## Thin Filament Properties: arranged in the same manner as the
        thick filament properties, but for the eight thin filaments

        thin_location:
            each tuple location is a list of x axis locations
        thin_link:
            each tuple location is a list consisting of entries (one for each
            thin_site on the thin_filament) of either a None or a link to a
            thick_crown
        thin_adjacent:
            each tuple location is a tuple of links to adjacent thick filaments
        thin_face:
            each tuple location is a tuple of length three, each location of
            which contains a tuple of links to thin filament sites that are
            facing each surrounding thick filament
        thin_site_spacing:
            the axial distance from one thin filament binding site to another
        thin_k:
            a single value, the spring constant of the thin filament between
            any given pair of thin binding sites

        """
        # Versioning, to be updated when backwards incompatible changes to the
        # data structure are made, not on release of new features
        self.version = 1.2
        # Parse initial LS and Z-line
        if time_dependence is not None:
            if 'lattice_spacing' in time_dependence:
                lattice_spacing = time_dependence['lattice_spacing'][0]
            if 'z_line' in time_dependence:
                z_line = time_dependence['z_line'][0]
            # actin permissiveness is set below, after thin filament creation
        self.time_dependence = time_dependence
        # The next few lines use detection of None rather than a sensible
        # default value as a passed None is an explicit selection of default
        if lattice_spacing is None:
            lattice_spacing = 14.0
        if z_line is None:
            z_line = 1250
        if poisson is None:
            poisson = 0.0
        # Record initial values for use with poisson driven ls
        self._initial_z_line = z_line
        self._initial_lattice_spacing = lattice_spacing
        self.poisson_ratio = poisson
        # Store these values for posterity
        self.lattice_spacing = lattice_spacing
        self.z_line = z_line
        # Create the thin filaments, unlinked but oriented on creation.
        thin_orientations = ([4, 0, 2], [3, 5, 1], [4, 0, 2], [3, 5, 1],
                             [3, 5, 1], [4, 0, 2], [3, 5, 1], [4, 0, 2])
        # noinspection PyArgumentList
        np.random.seed()
        if starts is None:
            thin_starts = [np.random.randint(25) for _ in thin_orientations]
        else:
            thin_starts = starts[0]
        self._thin_starts = thin_starts
        thin_ids = range(len(thin_orientations))
        new_thin = lambda thin_id: af.ThinFilament(self, thin_id, thin_orientations[thin_id],
                                                   thin_starts[thin_id])
        self.thin = tuple([new_thin(thin_id) for thin_id in thin_ids])
        # Determine the hiding line
        self.hiding_line = None
        self.update_hiding_line()
        # Create the thick filaments, remembering they are arranged thus:
        # ----------------------------
        # |   Actin around myosin    |
        # |--------------------------|
        # |      a1      a3          |
        # |  a0      a2      a0      |
        # |      M0      M1          |
        # |  a4      a6      a4      |
        # |      a5      a7      a5  |
        # |          M2      M3      |
        # |      a1      a3      a1  |
        # |          a2      a0      |
        # ----------------------------
        # and that when choosing which actin face to link to which thick
        # filament face, use these face orders:
        # ----------------------------------------------------
        # | Myosin face order  |       Actin face order      |
        # |--------------------|-----------------------------|
        # |         a1         |                             |
        # |     a0      a2     |  m0      m1         m0      |
        # |         mf         |      af      OR             |
        # |     a5      a3     |                     af      |
        # |         a4         |      m2         m2      m1  |
        # ----------------------------------------------------
        if starts is None:
            thick_starts = [np.random.randint(1, 4) for _ in range(4)]
        else:
            thick_starts = starts[1]
        self._thick_starts = thick_starts
        self.thick = (
            mf.ThickFilament(self, 0, (
                self.thin[0].thin_faces[1], self.thin[1].thin_faces[2],
                self.thin[2].thin_faces[2], self.thin[6].thin_faces[0],
                self.thin[5].thin_faces[0], self.thin[4].thin_faces[1]),
                             thick_starts[0]),
            mf.ThickFilament(self, 1, (
                self.thin[2].thin_faces[1], self.thin[3].thin_faces[2],
                self.thin[0].thin_faces[2], self.thin[4].thin_faces[0],
                self.thin[7].thin_faces[0], self.thin[6].thin_faces[1]),
                             thick_starts[1]),
            mf.ThickFilament(self, 2, (
                self.thin[5].thin_faces[1], self.thin[6].thin_faces[2],
                self.thin[7].thin_faces[2], self.thin[3].thin_faces[0],
                self.thin[2].thin_faces[0], self.thin[1].thin_faces[1]),
                             thick_starts[2]),
            mf.ThickFilament(self, 3, (
                self.thin[7].thin_faces[1], self.thin[4].thin_faces[2],
                self.thin[5].thin_faces[2], self.thin[1].thin_faces[0],
                self.thin[0].thin_faces[0], self.thin[3].thin_faces[1]),
                             thick_starts[3])
        )
        # Now the thin filaments need to be linked to thick filaments, use
        # the face orders from above and the following arrangement:
        # ----------------------------
        # |   Myosin around actin    |
        # |--------------------------|
        # |      m3      m2      m3  |
        # |          A1      A3      |
        # |      A0      A2          |
        # |  m1      m0      m1      |
        # |      A4      A6          |
        # |          A5      A7      |
        # |      m3      m2      m3  |
        # ----------------------------
        # The following may be hard to read, but it has been checked and
        # may be moderately trusted. CDW-20100406
        self.thin[0].set_thick_faces((self.thick[3].thick_faces[4],
                                      self.thick[0].thick_faces[0], self.thick[1].thick_faces[2]))
        self.thin[1].set_thick_faces((self.thick[3].thick_faces[3],
                                      self.thick[2].thick_faces[5], self.thick[0].thick_faces[1]))
        self.thin[2].set_thick_faces((self.thick[2].thick_faces[4],
                                      self.thick[1].thick_faces[0], self.thick[0].thick_faces[2]))
        self.thin[3].set_thick_faces((self.thick[2].thick_faces[3],
                                      self.thick[3].thick_faces[5], self.thick[1].thick_faces[1]))
        self.thin[4].set_thick_faces((self.thick[1].thick_faces[3],
                                      self.thick[0].thick_faces[5], self.thick[3].thick_faces[1]))
        self.thin[5].set_thick_faces((self.thick[0].thick_faces[4],
                                      self.thick[2].thick_faces[0], self.thick[3].thick_faces[2]))
        self.thin[6].set_thick_faces((self.thick[0].thick_faces[3],
                                      self.thick[1].thick_faces[5], self.thick[2].thick_faces[1]))
        self.thin[7].set_thick_faces((self.thick[1].thick_faces[4],
                                      self.thick[3].thick_faces[0], self.thick[2].thick_faces[2]))
        # Set the timestep for all our new cross-bridges
        self.timestep_len = timestep_len
        # Set actin_permissiveness for all our new binding sites
        if time_dependence is not None:
            if 'actin_permissiveness' in time_dependence:
                actin_permissiveness = \
                    time_dependence['actin_permissiveness'][0]
        if actin_permissiveness is None:
            actin_permissiveness = 1.0
        self.actin_permissiveness = actin_permissiveness
        # Track how long we've been running
        self.current_timestep = 0

        # ## variables previously initialized in methods (hiding line included above)
        self.last_transitions = None
        self.tm_transitions = None

    def to_dict(self):
        """Create a JSON compatible representation of the thick filament

        Example usage: json.dumps(sarc.to_dict(), indent=1)

        Current output includes:
            version: version of the sarcomere model
            timestep_len: the length of the timestep in ms
            current_timestep: time to get a watch
            lattice_spacing: the thick to thin distance
            z_line: the z_line location
            hiding_line: where binding sites become unavailable due to overlap
            time_dependence: how "lattice_spacing", "z_line", and
                "actin_permissiveness" can change
            last_transitions: keeps track of the last state change by thick
                filament and by crown
            thick: the structures for the thick filaments
            thin: the structures for the thin filaments
        """
        sd = self.__dict__.copy()  # sarc dict
        sd['current_timestep'] = self.current_timestep
        # set act_perm as mean since prop access returns values at every point
        sd['actin_permissiveness'] = np.mean(self.actin_permissiveness)
        sd['thick'] = [t.to_dict() for t in sd['thick']]
        sd['thin'] = [t.to_dict() for t in sd['thin']]
        return sd

    def from_dict(self, sd):
        """ Load values from a sarcomere dict. Values read in correspond to
        the current output documented in to_dict.
        """
        # Warn of possible version mismatches
        read, current = sd['version'], self.version
        if read != current:
            import warnings
            warnings.warn("Versioning mismatch, reading %0.1f into %0.1f."
                          % (read, current))
        # Get filaments in right orientations
        self.__init__(
            lattice_spacing=sd['_initial_lattice_spacing'],
            z_line=sd['_initial_z_line'],
            poisson=sd['poisson_ratio'],
            actin_permissiveness=sd['actin_permissiveness'],
            timestep_len=sd['timestep_len'],
            time_dependence=sd['time_dependence'],
            starts=(sd['_thin_starts'], sd['_thick_starts'])
        )
        # Local keys
        self.current_timestep = sd['current_timestep']
        self._z_line = sd['_z_line']
        self._lattice_spacing = sd['_lattice_spacing']
        self.hiding_line = sd['hiding_line']
        if 'last_transitions' in sd.keys():
            self.last_transitions = sd['last_transitions']
        # Sub-structure keys
        for data, thick in zip(sd['thick'], self.thick):
            thick.from_dict(data)
        for data, thin in zip(sd['thin'], self.thin):
            thin.from_dict(data)

    def run(self, time_steps=100, callback=None, bar=True, every=5):
        """Run the model for the specified number of timesteps

        Parameters:
            time_steps: number of time steps to run the model for (100)
            callback: function to be executed after each time step to
                collect data. The callback function takes the sarcomere
                in its current state as its only argument. (Defaults to
                the axial force at the M-line if not specified.)
            bar: progress bar control,False means don't display, True
                means give us the basic progress reports, if a function
                is passed, it will be called as f(completed_steps,
                total_steps, sec_left, sec_passed, process_name).
                (Defaults to True)
            every: how many time_steps to update after
        Returns:
            output: the results of the callback after each timestep
        """
        # Callback defaults to the axial force at the M-line
        if callback is None:
            callback = self.axial_force
        # ## logic to handle bar is type(True || False || Function)
        use_bar = False
        update_bar = self.print_bar
        if isinstance(bar, bool):
            use_bar = bar
        elif isinstance(bar, type(lambda x: x)):
            use_bar = True
            update_bar = bar
        # Create a place to store callback information and note the time
        output = []
        tic = time.time()
        # Run through each timestep
        for i in range(time_steps):
            try:
                self.timestep()
                output.append(callback())
                # Update us on how it went
                toc = int((time.time() - tic) / (i + 1) * (time_steps - i - 1))
                proc_name = mp.current_process().name

                if use_bar and i % every == 0:
                    update_bar(i=i, time_steps=time_steps,
                               toc=toc, tic=time.time() - tic,
                               proc_name=proc_name, output=output)
            except KeyboardInterrupt:
                return output, 130
            except Exception as e:
                import traceback
                print("/n")
                print(e)
                traceback.print_exc()
                return output, 1
        return output, 0

    @staticmethod
    def print_bar(i, time_steps, toc, proc_name, **bar_kwargs):
        if 'tic' in bar_kwargs.keys() and bar_kwargs['tic'] < -1:
            print('Causality has failed')
        sys.stdout.write("\n" + proc_name +
                         " finished timestep %i of %i, %ih%im%is left"
                         % (i + 1, time_steps, toc / 60 / 60, toc / 60 % 60, toc % 60))
        sys.stdout.flush()

    def timestep(self, current=None):
        """Move the model one step forward in time, allowing the
        myosin heads a chance to bind and then balancing forces
        """
        # Record our passage through time
        if current is not None:
            self.current_timestep = current
        else:
            self.current_timestep += 1
        # Update bound states
        self.last_transitions = [thick.transition() for thick in self.thick]
        # Settle forces
        self.settle()

    @property
    def current_timestep(self):
        """Return the current timestep"""
        return self._current_timestep

    @current_timestep.setter
    def current_timestep(self, new_timestep):
        """Set the current timestep"""
        # Update boundary conditions
        self.update_hiding_line()
        td = self.time_dependence
        i = new_timestep
        if td is not None:
            if 'lattice_spacing' in td:
                self.lattice_spacing = td['lattice_spacing'][i]
            if 'z_line' in td:
                self.z_line = td['z_line'][i]
            if 'actin_permissiveness' in td:
                self.actin_permissiveness = td['actin_permissiveness'][i]
        self._current_timestep = i
        return

    @property
    def actin_permissiveness(self):
        """How active & open to binding, 0 to 1, are binding sites?"""
        return [thin.permissiveness for thin in self.thin]

    @actin_permissiveness.setter
    def actin_permissiveness(self, new_permissiveness):
        """Assign all binding sites the new permissiveness, 0 to 1"""
        for thin in self.thin:
            thin.permissiveness = new_permissiveness

    @property
    def z_line(self):
        """Axial location of the z-line, length of the half sarcomere"""
        return self._z_line

    @z_line.setter
    def z_line(self, new_z_line):
        """Set a new z-line, updating the lattice spacing at the same time"""
        self._z_line = new_z_line
        self.update_ls_from_poisson_ratio()

    @property
    def lattice_spacing(self):
        """Return the current lattice spacing"""
        return self._lattice_spacing

    @lattice_spacing.setter
    def lattice_spacing(self, new_lattice_spacing):
        """Assign a new lattice spacing"""
        self._lattice_spacing = new_lattice_spacing

    @staticmethod
    def ls_to_d10(face_dist):
        """Convert face-to-face lattice spacing to d10 spacing.

        Governing equations:
            ls = ftf, the face to face distance
            filcenter_dist = face_dist + .5 * dia_actin + .5 * dia_myosin
            d10 = 1.5 * filcenter_dist
        Values:
            dia_actin: 9nm [1]_
            dia_myosin: 16nm [2]_
            example d10: 37nm for cardiac muscle at 2.2um [3]_
        References:
            .. [1] Egelman 1985, The structure of F-actin.
                   J Muscle Res Cell Motil, Pg 130, values from 9 to 10 nm
            .. [2] Woodhead et al. 2005, Atomic model of a myosin filament in
                   the relaxed state. Nature, Pg 1195, in tarantula filament
            .. [3] Millman 1998, The filament lattice of striated muscle.
                   Physiol Rev,  Pg 375
        Note: Arguably this should be moved to a support class as it really
        isn't something the half-sarcomere knows about or does. I'm leaving it
        here as a convenience for now.

        Parameters:
            face_dist: face to face lattice spacing in nm
        Returns:
            d10: d10 spacing in nm
        """
        filcenter_dist = face_dist + 0.5 * 9 + 0.5 * 16
        d10 = 1.5 * filcenter_dist
        return d10

    @staticmethod
    def d10_to_ls(d10):
        """Convert d10 spacing to face-to-face lattice spacing

        Governing equations: See ls_to_d10
        Values: See ls_to_d10

        Parameters:
            d10: d10 spacing in nm
        Returns:
            face_dist: face to face lattice spacing in nm
        """
        filcenter_dist = d10 * 2 / 3
        face_dist = filcenter_dist - 0.5 * 9 - 0.5 * 16
        return face_dist

    def axial_force(self):
        """Sum of each thick filament's axial force on the M-line """
        return sum([thick.effective_axial_force() for thick in self.thick])

    def radial_tension(self):
        """The sum of the thick filaments' radial tensions"""
        return sum([t.radial_tension() for t in self.thick])

    def radial_force(self):
        """The sum of the thick filaments' radial forces, as a (y,z) vector"""
        return np.sum([t.radial_force_of_filament() for t in self.thick], 0)

    def _single_settle(self, factor=0.95):
        """Settle down now, just a little bit"""
        thick = [thick.settle(factor) for thick in self.thick]
        thin = [thin.settle(factor) for thin in self.thin]
        return np.max((np.max(np.abs(thick)), np.max(np.abs(thin))))

    def settle(self):
        """Jiggle those locations around until the residual forces are low

        We choose the convergence limit so that 95% of thermal forcing events
        result in a deformation that produces more axial force than the
        convergence value, 0.12pN.
        """
        converge_limit = 0.12  # see doc string
        converge = self._single_settle()
        while converge > converge_limit:
            converge = self._single_settle()

    def _get_residual(self):
        """Get the residual force at every point in the half-sarcomere"""
        thick_f = np.hstack([t.axial_force() for t in self.thick])
        thin_f = np.hstack([t.axial_force() for t in self.thin])
        mash = np.hstack([thick_f, thin_f])
        return mash

    def get_frac_in_states(self):
        """Calculate the fraction of cross-bridges in each state"""
        nested = [t.get_states() for t in self.thick]
        xb_states = [xb for fil in nested for face in fil for xb in face]
        num_in_state = [xb_states.count(state) for state in range(3)]
        frac_in_state = [n / float(len(xb_states)) for n in num_in_state]
        return frac_in_state

    def update_ls_from_poisson_ratio(self):
        """Update the lattice spacing consistent with the poisson ratio,
        initial lattice spacing, current z-line, and initial z-line

        Governing equations
        ===================
        Poisson ratio := ν
            ν = dε_r/dε_z = Δr/r_0 / Δz/z_0
        From Mathematica derivation
        γ := center to center distance between filaments
            γ(ν, γ_0, z_0, Δz) = γ_0 (z_0/(z_0+Δz))^ν
        And since we want the face-to-face distance, aka ls, we convert with:
            γ = ls + 0.5 (dia_actin + dia_myosin)
        and
            γ_0 = ls_0 + 0.5 (dia_actin + dia_myosin)
        and the simplifying
            β = 0.5 (dia_actin + dia_myosin)
        to get
            ls = (ls_0 + β) (z_0/(z_0 + Δz))^ν - β
        which is what we implement below.
        Note: this is a novel derivation and so there is no current
            citation to be invoked.

        Values: See ls_to_d10

        Parameters:
            self
        Returns:
            None
        """
        beta = 0.5 * (9 + 16)
        ls_0 = self._initial_lattice_spacing
        z_0 = self._initial_z_line
        nu = self.poisson_ratio
        dz = self.z_line - z_0
        ls = (ls_0 + beta) * (z_0 / (z_0 + dz)) ** nu - beta
        self.lattice_spacing = ls
        return

    def update_hiding_line(self):
        """Update the line determining which actin sites are unavailable"""
        farthest_actin = min([min(thin.axial) for thin in self.thin])
        self.hiding_line = -farthest_actin

    def resolve_address(self, address):
        """Give back a link to the object specified in the address
        Addresses are formatted as the object type (string) followed by a list
        of the indices that the object occupies in each level of organization.
        Valid string values are:
            thin_fil
            thin_face
            bs
            thick_fil
            crown
            thick_face
            xb
        and an example valid address would be ('bs', 1, 14) for the binding
        site at index 14 on the thin filament at index 1.
        """
        if address[0] == 'thin_fil':
            return self.thin[address[1]]
        elif address[0] in ['thin_face', 'bs']:
            return self.thin[address[1]].resolve_address(address)
        elif address[0] == 'thick_fil':
            return self.thick[address[1]]
        elif address[0] in ['crown', 'thick_face', 'xb']:
            return self.thick[address[1]].resolve_address(address)
        import warnings
        warnings.warn("Unresolvable address: %s" % str(address))


sarc = hs()
