"""
Test the results packages when collecting from the public qcarchive.
"""

import pytest
from qcportal import FractalClient

from qcsubmit.results import (
    BasicCollectionResult,
    OptimizationCollectionResult,
    TorsionDriveCollectionResult,
)
from qcsubmit.testing import temp_directory


@pytest.fixture
def public_client():
    """Setup a new connection to the public qcarchive client."""

    return FractalClient()


def test_optimization_default_results(public_client):
    """
    Test collecting results from the public qcarchive.
    The optimization collection is small containing only 302 records however some are incomplete and only 150
    unique molecules should be pulled.
    """

    result = OptimizationCollectionResult.from_server(
        client=public_client,
        spec_name="default",
        dataset_name="OpenFF Gen 2 Opt Set 1 Roche",
        include_trajectory=False,
        final_molecule_only=False)

    assert result.n_molecules == 150
    assert result.n_results == 298
    assert result.method == "b3lyp-d3bj"
    assert result.basis == "dzvp"
    assert result.dataset_name == "OpenFF Gen 2 Opt Set 1 Roche"
    assert result.program == "psi4"

    # by default the result should pull the initial and final molecule only
    for optimization in result.collection.values():
        for entry in optimization.entries:
            assert len(entry.trajectory) == 2

            for single_result in entry.trajectory:
                assert single_result.wbo is not None
                assert single_result.mbo is not None


def test_optimization_trajectory_results(public_client):
    """
    Test downloading an optimization result with the trajectory.
    """

    # just take the first molecule in the set as the download can be slow
    result = OptimizationCollectionResult.from_server(
        client=public_client,
        spec_name="default",
        dataset_name="OpenFF Gen 2 Opt Set 1 Roche",
        include_trajectory=True,
        final_molecule_only=False,
        subset=["cn1c(cccc1=o)c2ccccc2oc-0"])

    # make sure one unique molecule is found
    assert result.n_molecules == 1
    assert result.n_results == 1

    # get the optimization result
    opt_result = result.collection["Cn1c(cccc1=O)c2ccccc2OC"]
    # check connectivity changes
    assert opt_result.detect_connectivity_changes_heuristic() == {0: False}
    assert opt_result.detect_connectivity_changes_wbo() == {0: False}

    # check hydrogen bonds
    assert opt_result.detect_hydrogen_bonds_heuristic() == {0: False}
    assert opt_result.detect_hydrogen_bonds_wbo() == {0: False}

    # make sure the full trajectory was pulled out
    assert opt_result.n_entries == 1
    traj = opt_result.entries[0]

    molecule = traj.get_trajectory()

    assert molecule.n_conformers == 59
    assert len(traj.energies) == molecule.n_conformers


def test_optimization_final_only_result(public_client):
    """
    Test gathering a result with only the final molecules in the records.
    """

    result = OptimizationCollectionResult.from_server(
        client=public_client,
        spec_name="default",
        dataset_name="OpenFF Gen 2 Opt Set 1 Roche",
        include_trajectory=False,
        final_molecule_only=True)

    for optimization in result.collection.values():
        for entry in optimization.entries:
            assert len(entry.trajectory) == 1


def test_optimization_export_round_trip(public_client):
    """Test exporting the results to file and back."""

    with temp_directory():
        result = OptimizationCollectionResult.from_server(
            client=public_client,
            spec_name="default",
            dataset_name="OpenFF Gen 2 Opt Set 1 Roche",
            include_trajectory=False,
            final_molecule_only=True)

        result.export_results("dataset.json")

        # now load the dataset back in
        result2 = OptimizationCollectionResult.parse_file("dataset.json")

        assert result.dict(exclude={"collection"}) == result2.dict(exclude={"collection"})


def test_basicdataset_result(public_client):
    """
    Test downloading a default dataset.
    """

    result = BasicCollectionResult.from_server(
        client=public_client,
        dataset_name="OpenFF Gen 2 Opt Set 1 Roche",
        spec_name="default",
        method="b3lyp-d3bj",
        basis="dzvp",
    )

    assert result.driver.value == "hessian"
    assert result.method == "b3lyp-d3bj"
    assert result.basis == "dzvp"
    assert result.n_molecules == 150
    assert result.n_results == 298


def test_basicdataset_export_round_trip(public_client):
    """
    Test basic dataset round tripping to file.
    """

    with temp_directory():
        result = BasicCollectionResult.from_server(
            client=public_client,
            dataset_name="OpenFF Gen 2 Opt Set 1 Roche",
            spec_name="default",
            method="b3lyp-d3bj",
            basis="dzvp",
        )

        result.export_results("dataset.json")

        result2 = BasicCollectionResult.parse_file("dataset.json")

        assert result.dict(exclude={"collection"}) == result2.dict(exclude={"collection"})
        for molecule in result.collection:
            assert molecule in result2.collection


def test_torsiondrivedataset_result_default(public_client):
    """
    Test downloading a basic torsiondrive dataset from the archive.
    """
    from simtk import unit
    import numpy as np

    result = TorsionDriveCollectionResult.from_server(client=public_client,
                                                      spec_name="default",
                                                      dataset_name="TorsionDrive Paper",
                                                      include_trajectory=False,
                                                      final_molecule_only=False)

    # now we need to make sure that each optimization traj has only one molecule in it.
    for torsiondrive in result.collection.values():
        for optimization in torsiondrive.optimization.values():
            assert len(optimization.trajectory) == 2

    # make sure the three torsiondrives are pulled
    assert len(result.collection) == 3

    # now check the utility functions
    torsiondrive = result.collection["[ch2:3]([ch2:2][oh:4])[oh:1]_12"]
    assert torsiondrive.final_energies is not None
    # make sure there is an energy of every result
    assert len(torsiondrive.final_energies) == len(torsiondrive.optimization)
    mol = torsiondrive.molecule
    molecule = torsiondrive.get_torsiondrive()
    assert mol == molecule
    # make sure the conformers are loaded onto the molecule
    assert molecule.n_conformers == len(torsiondrive.optimization)
    # now check each conformer
    ordered_results = torsiondrive.get_ordered_results()
    for conformer, single_result in zip(molecule.conformers, ordered_results):
        assert np.allclose(conformer.in_units_of(unit.bohr).tolist(), single_result[1].molecule.geometry.tolist())

    # now make sure the lowest energy optimization is recognized
    lowest_result = torsiondrive.get_lowest_energy_optimisation()
    all_energies = list(torsiondrive.final_energies.values())
    assert lowest_result.final_energy == min(all_energies)


def test_torsiondrivedataset_final_result_only(public_client):
    """
    Make sure the final_molecule_only keyword is working
    """

    result = TorsionDriveCollectionResult.from_server(client=public_client,
                                                      spec_name="default",
                                                      dataset_name="TorsionDrive Paper",
                                                      include_trajectory=False,
                                                      final_molecule_only=True)

    # now we need to make sure that each optimization traj has only one molecule in it.
    for torsiondrive in result.collection.values():
        for optimization in torsiondrive.optimization.values():
            assert len(optimization.trajectory) == 1


def test_torsiondrivedataset_traj_subset(public_client):
    """
    Make sure the full trajectories are pulled when requested for a subset of molecules in a collection.
    """

    result = TorsionDriveCollectionResult.from_server(client=public_client,
                                                      spec_name="default",
                                                      dataset_name="TorsionDrive Paper",
                                                      include_trajectory=True,
                                                      final_molecule_only=False,
                                                      subset=["[ch2:3]([ch2:2][oh:4])[oh:1]_12"])

    # make sure one torsiondrive was pulled down
    assert len(result.collection) == 1
    # now make sure the full trajectory is pulled
    torsiondrive = result.collection["[ch2:3]([ch2:2][oh:4])[oh:1]_12"]
    for optimization in torsiondrive.optimization.values():
        assert len(optimization.trajectory) > 2


def test_torsiondrivedataset_export(public_client):
    """
    Make sure that the torsiondrive datasets can be exported.
    """

    with temp_directory():
        result = TorsionDriveCollectionResult.from_server(client=public_client,
                                                          spec_name="default",
                                                          dataset_name="TorsionDrive Paper",
                                                          include_trajectory=False,
                                                          final_molecule_only=True)

        result.export_results("dataset.json")

        result2 = TorsionDriveCollectionResult.parse_file("dataset.json")

        assert result.dict(exclude={"collection"}) == result2.dict(exclude={"collection"})
        for molecule in result.collection:
            assert molecule in result2.collection
