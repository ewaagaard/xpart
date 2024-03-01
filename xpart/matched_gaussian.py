# copyright ############################### #
# This file is part of the Xpart Package.   #
# Copyright (c) CERN, 2021.                 #
# ######################################### #

import numpy as np

from .general import _print

from .longitudinal import generate_longitudinal_coordinates, _characterize_line
from .build_particles import build_particles

# To get the right Particles class depending on pyheatail interface state
import xpart as xp

def generate_matched_gaussian_bunch(num_particles,
                                    nemitt_x, nemitt_y, sigma_z,
                                    total_intensity_particles=None,
                                    particle_on_co=None,
                                    R_matrix=None,
                                    circumference=None,
                                    momentum_compaction_factor=None,
                                    rf_harmonic=None,
                                    rf_voltage=None,
                                    rf_phase=None,
                                    p_increment=0.,
                                    tracker=None,
                                    line=None,
                                    particle_ref=None,
                                    particles_class=None,
                                    engine=None,
                                    _context=None, _buffer=None, _offset=None,
                                    **kwargs,  # Passed to build_particles
                                    ):
    '''
    Generate a matched Gaussian bunch.

    Parameters
    ----------
    line : xpart.Line
        Line for which the bunch is generated.
    num_particles : int
        Number of particles to be generated.
    nemitt_x : float
        Normalized emittance in the horizontal plane (in m rad).
    nemitt_y : float
        Normalized emittance in the vertical plane (in m rad).
    sigma_z : float
        RMS bunch length in meters.
    total_intensity_particles : float
        Total intensity of the bunch in particles.

    Returns
    -------
    part : xpart.Particles
        Particles object containing the generated particles.

    '''

    if line is not None and tracker is not None:
        raise ValueError(
            'line and tracker cannot be provided at the same time.')

    if tracker is not None:
        _print(
            "The argument tracker is deprecated. Please use line instead.",
            DeprecationWarning)
        line = tracker.line

    if line is not None:
        assert line.tracker is not None, ("The line has no tracker. Please use "
                                          "`Line.build_tracker()`")

    if particle_ref is not None and particle_on_co is not None:
        raise ValueError("`particle_ref` and `particle_on_co`"
                         " cannot be provided at the same time")

    if particle_ref is None:
        if particle_on_co is not None:
            particle_ref = particle_on_co
        elif line is not None and line.particle_ref is not None:
            particle_ref = line.particle_ref
        else:
            raise ValueError(
                "`line`, `particle_ref` or `particle_on_co` must be provided!")

    zeta, delta = generate_longitudinal_coordinates(
        distribution='gaussian',
        num_particles=num_particles,
        particle_ref=(particle_ref if particle_ref is not None
                      else particle_on_co),
        line=line,
        circumference=circumference,
        momentum_compaction_factor=momentum_compaction_factor,
        rf_harmonic=rf_harmonic,
        rf_voltage=rf_voltage,
        rf_phase=rf_phase,
        p_increment=p_increment,
        sigma_z=sigma_z,
        engine=engine,
        **kwargs)

    assert len(zeta) == len(delta) == num_particles

    x_norm = np.random.normal(size=num_particles)
    px_norm = np.random.normal(size=num_particles)
    y_norm = np.random.normal(size=num_particles)
    py_norm = np.random.normal(size=num_particles)

    if total_intensity_particles is None:
        # go to particles.weight = 1
        total_intensity_particles = num_particles

    part = build_particles(_context=_context, _buffer=_buffer, _offset=_offset,
                           R_matrix=R_matrix,
                           particles_class=particles_class,
                           particle_on_co=particle_on_co,
                           particle_ref=(
                               particle_ref if particle_on_co is None
                               else None),
                           line=line,
                           zeta=zeta, delta=delta,
                           x_norm=x_norm, px_norm=px_norm,
                           y_norm=y_norm, py_norm=py_norm,
                           nemitt_x=nemitt_x, nemitt_y=nemitt_y,
                           weight=total_intensity_particles / num_particles,
                           **kwargs)
    return part


def split_scheme(filling_scheme, n_chunck=1):
    """
    Distribute the filling scheme between the processes, i.e. assign to each
    processor its bunches
    """
    total_n_bunches = len(filling_scheme.nonzero()[0])
    if n_chunck > 1:

        # create the array containing the id of the bunches on each rank
        # (copied from PyHEADTAIL.mpi.mpi_data)
        n_bunches = total_n_bunches
        n_bunches_on_rank = [n_bunches//n_chunck+1 if i < n_bunches % n_chunck
                             else n_bunches // n_chunck + 0
                             for i in range(n_chunck)]
        n_tasks_cumsum = np.insert(np.cumsum(n_bunches_on_rank), 0, 0)
        total_bunch_ids = np.unique(
            np.cumsum(filling_scheme == 1)) - 1
        bunches_per_rank = [total_bunch_ids[n_tasks_cumsum[i]:
                                            n_tasks_cumsum[i + 1]]
                            for i in range(n_chunck)]
    else:
        bunches_per_rank = [np.linspace(0,
                                        total_n_bunches - 1,
                                        total_n_bunches)]

    return bunches_per_rank


def generate_matched_gaussian_multibunch_beam(filling_scheme,
                                              num_particles,
                                              nemitt_x, nemitt_y, sigma_z,
                                              total_intensity_particles=None,
                                              particle_on_co=None,
                                              R_matrix=None,
                                              circumference=None,
                                              momentum_compaction_factor=None,
                                              rf_harmonic=None,
                                              rf_voltage=None,
                                              rf_phase=None,
                                              bucket_length = None,
                                              p_increment=0.,
                                              tracker=None,
                                              line=None,
                                              particle_ref=None,
                                              particles_class=None,
                                              engine=None,
                                              _context=None, _buffer=None, _offset=None,
                                              bunch_numbers=None,
                                              bunch_spacing_buckets=1,
                                              **kwargs,  # Passed to build_particles
                                              ):

    assert ((line is not None and particle_ref is not None) or
            (rf_harmonic is not None and rf_voltage is not None) or
            bucket_length is not None)
            
    if circumference is None:
        circumference = line.get_length()
    assert circumference > 0.0
            
    if bucket_length is not None:
        assert (rf_harmonic is None and rf_voltage is None),(
                'Cannot provide bucket length together with RF voltage+harmonic')
    else:
        if rf_harmonic is not None and rf_voltage is not None:
            main_harmonic_number = rf_harmonic[np.argmax(rf_voltage)]
        else:
            dct_line = _characterize_line(line, particle_ref)
            assert len(dct_line['voltage_list']) > 0
            main_harmonic_number = int(np.floor(
                        dct_line['h_list'][np.argmax(dct_line['voltage_list'])]+0.5))
        bucket_length = circumference/main_harmonic_number
    bunch_spacing = bunch_spacing_buckets * bucket_length
    assert len(filling_scheme) == np.floor(circumference/bunch_spacing+0.5)

    if bunch_numbers is None:
        bunch_numbers = range(len(filling_scheme.nonzero()[0]))

    macro_bunch = generate_matched_gaussian_bunch(
        num_particles=num_particles * len(bunch_numbers),
        nemitt_x=nemitt_x, nemitt_y=nemitt_y, sigma_z=sigma_z,
        total_intensity_particles=total_intensity_particles,
        particle_on_co=particle_on_co,
        R_matrix=R_matrix,
        circumference=circumference,
        momentum_compaction_factor=momentum_compaction_factor,
        rf_harmonic=rf_harmonic,
        rf_voltage=rf_voltage,
        rf_phase=rf_phase,
        p_increment=p_increment,
        tracker=tracker,
        line=line,
        particle_ref=particle_ref,
        particles_class=particles_class,
        engine=engine,
        _context=_context, _buffer=_buffer, _offset=_offset,
        **kwargs,  # They are passed to build_particles
    )

    filled_buckets = filling_scheme.nonzero()[0]
    count = 0
    for bunch_number in bunch_numbers:
        bucket_n = filled_buckets[bunch_number]
        macro_bunch.zeta[count * num_particles:
                         (count+1) * num_particles] += (bunch_spacing *
                                                        bucket_n)
        count += 1

    return macro_bunch
