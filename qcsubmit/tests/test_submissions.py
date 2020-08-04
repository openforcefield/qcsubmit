"""
Test submissions to a local qcarchive instance using different compute backends, RDKit, OpenMM, PSI4

Here we use the qcfractal fractal_compute_server fixture to set up the database.
"""

import pytest
from openforcefield.topology import Molecule
from qcengine.testing import has_program
from qcfractal.testing import fractal_compute_server
from qcportal import FractalClient

from qcsubmit.common_structures import Metadata
from qcsubmit.datasets import BasicDataset, OptimizationDataset, TorsiondriveDataset
from qcsubmit.exceptions import DatasetInputError
from qcsubmit.factories import (
    BasicDatasetFactory,
    OptimizationDatasetFactory,
    TorsiondriveDatasetFactory,
)
from qcsubmit.utils import get_data


@pytest.mark.parametrize("specification", [
    pytest.param(({"method": "hf", "basis": "3-21g", "program": "psi4"}, "energy"), id="PSI4 hf 3-21g energy"),
    pytest.param(({"method": "openff-1.0.0", "basis": "smirnoff", "program": "openmm"}, "energy"), id="SMIRNOFF openff-1.0.0 energy"),
    pytest.param(({"method": "uff", "basis": None, "program": "rdkit"}, "gradient"), id="RDKit UFF gradient")
])
def test_basic_submissions_single_spec(fractal_compute_server, specification):
    """Test submitting a basic dataset to a snowflake server."""

    client = FractalClient(fractal_compute_server)

    qc_spec, driver = specification

    program = qc_spec["program"]
    if not has_program(program):
        pytest.skip(f"Program '{program}' not found.")

    molecules = Molecule.from_file(get_data("butane_conformers.pdb"), "pdb")

    factory = BasicDatasetFactory(driver=driver)
    factory.add_qc_spec(**qc_spec, spec_name="default",
                        spec_description="testing the single points",
                        overwrite=True)

    dataset = factory.create_dataset(dataset_name=f"Test single points info {program}, {driver}",
                                     molecules=molecules,
                                     description="Test basics dataset",
                                     tagline="Testing single point datasets",
                                     )

    with pytest.raises(DatasetInputError):
        dataset.submit(client=client, await_result=False)

    # now add a mock url so we can submit the data
    dataset.metadata.long_description_url = "https://test.org"

    # now submit again
    dataset.submit(client=client, await_result=False)

    fractal_compute_server.await_results()

    # make sure of the results are complete
    ds = client.get_collection("Dataset", dataset.dataset_name)

    # check the metadata
    meta = Metadata(**ds.data.metadata)
    assert meta == dataset.metadata

    assert ds.data.description == dataset.description
    assert ds.data.tagline == dataset.dataset_tagline
    assert ds.data.tags == dataset.dataset_tags

    # check the provenance
    assert dataset.provenance == ds.data.provenance

    # check the qc spec
    assert ds.data.default_driver == dataset.driver

    # get the last ran spec
    for specification in ds.data.history:
        driver, program, method, basis, spec_name = specification
        spec = dataset.qc_specifications[spec_name]
        assert driver == dataset.driver
        assert program == spec.program
        assert method == spec.method
        assert basis == spec.basis
        break
    else:
        raise RuntimeError(f"The requested compute was not found in the history {ds.data.history}")

    for spec in dataset.qc_specifications.values():
        query = ds.get_records(
            method=spec.method,
            basis=spec.basis,
            program=spec.program,
        )
        for index in query.index:
            result = query.loc[index].record
            assert result.status.value.upper() == "COMPLETE"
            assert result.error is None
            assert result.return_result is not None


def test_basic_submissions_multiple_spec(fractal_compute_server):
    """Test submitting a basic dataset to a snowflake server with multiple qcspecs."""

    client = FractalClient(fractal_compute_server)

    qc_specs = [{"method": "openff-1.0.0", "basis": "smirnoff", "program": "openmm", "spec_name": "openff"},
                {"method": "gaff-2.11", "basis": "antechamber", "program": "openmm", "spec_name": "gaff"}]

    molecules = Molecule.from_file(get_data("butane_conformers.pdb"), "pdb")

    factory = BasicDatasetFactory(driver="energy")
    factory.clear_qcspecs()
    for spec in qc_specs:
        factory.add_qc_spec(**spec,
                            spec_description="testing the single points"
                            )

    dataset = factory.create_dataset(dataset_name=f"Test single points multiple specs",
                                     molecules=molecules,
                                     description="Test basics dataset",
                                     tagline="Testing single point datasets",
                                     )

    with pytest.raises(DatasetInputError):
        dataset.submit(client=client, await_result=False)

    # now add a mock url so we can submit the data
    dataset.metadata.long_description_url = "https://test.org"

    # now submit again
    dataset.submit(client=client, await_result=False)

    fractal_compute_server.await_results()

    # make sure of the results are complete
    ds = client.get_collection("Dataset", dataset.dataset_name)

    # check the metadata
    meta = Metadata(**ds.data.metadata)
    assert meta == dataset.metadata

    assert ds.data.description == dataset.description
    assert ds.data.tagline == dataset.dataset_tagline
    assert ds.data.tags == dataset.dataset_tags

    # check the provenance
    assert dataset.provenance == ds.data.provenance

    # check the qc spec
    assert ds.data.default_driver == dataset.driver

    # get the last ran spec
    for specification in ds.data.history:
        driver, program, method, basis, spec_name = specification
        spec = dataset.qc_specifications[spec_name]
        assert driver == dataset.driver
        assert program == spec.program
        assert method == spec.method
        assert basis == spec.basis

    for spec in dataset.qc_specifications.values():
        query = ds.get_records(
            method=spec.method,
            basis=spec.basis,
            program=spec.program,
        )
        for index in query.index:
            result = query.loc[index].record
            assert result.status.value.upper() == "COMPLETE"
            assert result.error is None
            assert result.return_result is not None


@pytest.mark.parametrize("dataset_data", [
    pytest.param((BasicDatasetFactory, BasicDataset), id="Dataset"),
    pytest.param((OptimizationDatasetFactory, OptimizationDataset), id="OptimizationDataset"),
    pytest.param((TorsiondriveDatasetFactory, TorsiondriveDataset), id="TorsiondriveDataset")
])
def test_adding_compute(fractal_compute_server, dataset_data):
    """
    Test adding new compute to each of the dataset types using none psi4 programs.
    """
    client = FractalClient(fractal_compute_server)
    mol = Molecule.from_smiles("CO")
    factory_type, dataset_type = dataset_data
    # make and clear out the qc specs
    factory = factory_type()
    factory.clear_qcspecs()
    factory.add_qc_spec(method="openff-1.0.0",
                        basis="smirnoff",
                        program="openmm",
                        spec_name="default",
                        spec_description="default spec for openff")
    dataset = factory.create_dataset(dataset_name=f"Test adding compute to {factory_type}",
                                     molecules=mol,
                                     description=f"Testing adding compute to a {dataset_type} dataset",
                                     tagline="tests for adding compute.")

    # now add a mock url so we can submit the data
    dataset.metadata.long_description_url = "https://test.org"

    # now submit again
    dataset.submit(client=client, await_result=False)
    # make sure that the compute has finished
    fractal_compute_server.await_results()
    fractal_compute_server.await_services(max_iter=50)

    # now lets make a dataset with new compute and submit it
    # transfer the metadata to compare the elements
    compute_dataset = dataset_type(dataset_name=dataset.dataset_name, metadata=dataset.metadata)
    compute_dataset.clear_qcspecs()
    # now add the new compute spec
    compute_dataset.add_qc_spec(method="uff",
                                basis=None,
                                program="rdkit",
                                spec_name="rdkit",
                                spec_description="rdkit basic spec")

    # make sure the dataset has no molecules and submit it
    assert compute_dataset.dataset == {}
    compute_dataset.submit(client=client)
    # make sure that the compute has finished
    fractal_compute_server.await_results()
    fractal_compute_server.await_services(max_iter=50)

    # make sure of the results are complete
    ds = client.get_collection(dataset.dataset_type, dataset.dataset_name)

    # check the metadata
    meta = Metadata(**ds.data.metadata)
    assert meta == dataset.metadata

    assert ds.data.description == dataset.description
    assert ds.data.tagline == dataset.dataset_tagline
    assert ds.data.tags == dataset.dataset_tags

    # check the provenance
    assert dataset.provenance == ds.data.provenance

    # update all specs into one dataset
    dataset.add_qc_spec(**compute_dataset.qc_specifications["rdkit"].dict())
    # get the last ran spec
    if dataset.dataset_type == "DataSet":
            for specification in ds.data.history:
                driver, program, method, basis, spec_name = specification
                spec = dataset.qc_specifications[spec_name]
                assert driver == dataset.driver
                assert program == spec.program
                assert method == spec.method
                assert basis == spec.basis

            for spec in dataset.qc_specifications.values():
                query = ds.get_records(
                    method=spec.method,
                    basis=spec.basis,
                    program=spec.program,
                )
                for index in query.index:
                    result = query.loc[index].record
                    assert result.status.value.upper() == "COMPLETE"
                    assert result.error is None
                    assert result.return_result is not None
    else:
        # check the qc spec
        for qc_spec in dataset.qc_specifications.values():
            spec = ds.data.specs[qc_spec.spec_name]

            assert spec.description == qc_spec.spec_description
            assert spec.qc_spec.driver == dataset.driver
            assert spec.qc_spec.method == qc_spec.method
            assert spec.qc_spec.basis == qc_spec.basis
            assert spec.qc_spec.program == qc_spec.program

            # check the keywords
            keywords = client.query_keywords(spec.qc_spec.keywords)[0]

            assert keywords.values["maxiter"] == dataset.maxiter
            assert keywords.values["scf_properties"] == dataset.scf_properties

            # query the dataset
            ds.query(qc_spec.spec_name)

            for index in ds.df.index:
                record = ds.df.loc[index].default
                # this will take some time so make sure it is running with no error
                assert record.status.value == "COMPLETE", print(record.dict())
                assert record.error is None


def test_basic_submissions_wavefunction(fractal_compute_server):
    """
    Test submitting a basic dataset with a wavefunction protocol and make sure it is executed.
    """
    # only a psi4 test
    if not has_program("psi4"):
        pytest.skip(f"Program psi4 not found.")

    client = FractalClient(fractal_compute_server)
    molecules = Molecule.from_file(get_data("butane_conformers.pdb"), "pdb")

    factory = BasicDatasetFactory(driver="energy")
    factory.clear_qcspecs()
    factory.add_qc_spec(method="hf",
                        basis="sto-3g",
                        program="psi4",
                        spec_name="default",
                        spec_description="wavefunction spec",
                        store_wavefunction="orbitals_and_eigenvalues")

    dataset = factory.create_dataset(dataset_name=f"Test single points with wavefunction",
                                     molecules=molecules,
                                     description="Test basics dataset",
                                     tagline="Testing single point datasets with wavefunction",
                                     )
    # now add a mock url so we can submit the data
    dataset.metadata.long_description_url = "https://test.org"

    # submit the dataset
    # now submit again
    dataset.submit(client=client, await_result=False)

    fractal_compute_server.await_results()

    # make sure of the results are complete
    ds = client.get_collection("Dataset", dataset.dataset_name)

    # check the metadata
    meta = Metadata(**ds.data.metadata)
    assert meta == dataset.metadata

    assert ds.data.description == dataset.description
    assert ds.data.tagline == dataset.dataset_tagline
    assert ds.data.tags == dataset.dataset_tags

    # check the provenance
    assert dataset.provenance == ds.data.provenance

    # check the qc spec
    assert ds.data.default_driver == dataset.driver

    # get the last ran spec
    for specification in ds.data.history:
        driver, program, method, basis, spec_name = specification
        spec = dataset.qc_specifications[spec_name]
        assert driver == dataset.driver
        assert program == spec.program
        assert method == spec.method
        assert basis == spec.basis

    for spec in dataset.qc_specifications.values():
        query = ds.get_records(
            method=spec.method,
            basis=spec.basis,
            program=spec.program,
        )
        for index in query.index:
            result = query.loc[index].record
            assert result.status.value.upper() == "COMPLETE"
            assert result.error is None
            assert result.return_result is not None
            basis = result.get_wavefunction("basis")
            assert basis.name.lower() == "sto-3g"
            orbitals = result.get_wavefunction("orbitals_a")
            assert orbitals.shape is not None


@pytest.mark.parametrize("specification", [
    pytest.param(({"method": "hf", "basis": "3-21g", "program": "psi4"}, "gradient"), id="PSI4 hf 3-21g gradient"),
    pytest.param(({"method": "openff_unconstrained-1.0.0", "basis": "smirnoff", "program": "openmm"}, "gradient"), id="SMIRNOFF openff_unconstrained-1.0.0 gradient"),
    pytest.param(({"method": "uff", "basis": None, "program": "rdkit"}, "gradient"), id="RDKit UFF gradient")
])
def test_optimization_submissions(fractal_compute_server, specification):
    """Test submitting an Optimization dataset to a snowflake server."""

    client = FractalClient(fractal_compute_server)

    qc_spec, driver = specification
    program = qc_spec["program"]
    if not has_program(program):
        pytest.skip(f"Program '{program}' not found.")

    molecules = Molecule.from_file(get_data("butane_conformers.pdb"), "pdb")

    factory = OptimizationDatasetFactory(driver=driver)
    factory.add_qc_spec(**qc_spec, spec_name="default", spec_description="test", overwrite=True)

    dataset = factory.create_dataset(dataset_name=f"Test optimizations info {program}, {driver}",
                                     molecules=molecules[:2],
                                     description="Test optimization dataset",
                                     tagline="Testing optimization datasets",
                                     )

    with pytest.raises(DatasetInputError):
        dataset.submit(client=client, await_result=False)

    # now add a mock url so we can submit the data
    dataset.metadata.long_description_url = "https://test.org"

    # now submit again
    dataset.submit(client=client, await_result=False)

    fractal_compute_server.await_results()

    # make sure of the results are complete
    ds = client.get_collection("OptimizationDataset", dataset.dataset_name)

    # check the metadata
    meta = Metadata(**ds.data.metadata)
    assert meta == dataset.metadata

    # check the provenance
    assert dataset.provenance == ds.data.provenance

    # check the qc spec
    for qc_spec in dataset.qc_specifications.values():
        spec = ds.data.specs[qc_spec.spec_name]

        assert spec.description == qc_spec.spec_description
        assert spec.qc_spec.driver == dataset.driver
        assert spec.qc_spec.method == qc_spec.method
        assert spec.qc_spec.basis == qc_spec.basis
        assert spec.qc_spec.program == qc_spec.program

        # check the keywords
        keywords = client.query_keywords(spec.qc_spec.keywords)[0]

        assert keywords.values["maxiter"] == dataset.maxiter
        assert keywords.values["scf_properties"] == dataset.scf_properties

        # query the dataset
        ds.query(qc_spec.spec_name)

        for index in ds.df.index:
            record = ds.df.loc[index].default
            assert record.status.value == "COMPLETE"
            assert record.error is None
            assert len(record.trajectory) > 1
            # if we used psi4 make sure the properties were captured
            if program == "psi4":
                result = record.get_trajectory()[0]
                assert "CURRENT DIPOLE X" in result.extras["qcvars"].keys()
                assert "SCF QUADRUPOLE XX" in result.extras["qcvars"].keys()


@pytest.mark.parametrize("specification", [
    pytest.param(({"method": "openff_unconstrained-1.1.0", "basis": "smirnoff", "program": "openmm"}, "gradient"), id="SMIRNOFF openff_unconstrained-1.0.0 gradient"),
    pytest.param(({"method": "mmff94", "basis": None, "program": "rdkit"}, "gradient"), id="RDKit mmff94 gradient")
])
def test_torsiondrive_submissions(fractal_compute_server, specification):
    """
    Test submitting a torsiondrive dataset and computing it.
    """

    client = FractalClient(fractal_compute_server)

    qc_spec, driver = specification
    program = qc_spec["program"]
    if not has_program(program):
        pytest.skip(f"Program '{program}' not found.")

    molecules = Molecule.from_smiles("CO")

    factory = TorsiondriveDatasetFactory(driver=driver)
    factory.add_qc_spec(**qc_spec, spec_name="default", spec_description="test", overwrite=True)

    dataset = factory.create_dataset(dataset_name=f"Test torsiondrives info {program}, {driver}",
                                     molecules=molecules,
                                     description="Test torsiondrive dataset",
                                     tagline="Testing torsiondrive datasets",
                                     )

    with pytest.raises(DatasetInputError):
        dataset.submit(client=client, await_result=False)

    # now add a mock url so we can submit the data
    dataset.metadata.long_description_url = "https://test.org"

    # now submit again
    dataset.submit(client=client, await_result=False)

    fractal_compute_server.await_services(max_iter=50)

    # make sure of the results are complete
    ds = client.get_collection("TorsionDriveDataset", dataset.dataset_name)

    # check the metadata
    meta = Metadata(**ds.data.metadata)
    assert meta == dataset.metadata

    # check the provenance
    assert dataset.provenance == ds.data.provenance

    # check the qc spec
    for qc_spec in dataset.qc_specifications.values():
        spec = ds.data.specs[qc_spec.spec_name]

        assert spec.description == qc_spec.spec_description
        assert spec.qc_spec.driver == dataset.driver
        assert spec.qc_spec.method == qc_spec.method
        assert spec.qc_spec.basis == qc_spec.basis
        assert spec.qc_spec.program == qc_spec.program

        # check the keywords
        keywords = client.query_keywords(spec.qc_spec.keywords)[0]

        assert keywords.values["maxiter"] == dataset.maxiter
        assert keywords.values["scf_properties"] == dataset.scf_properties

        # query the dataset
        ds.query(qc_spec.spec_name)

        for index in ds.df.index:
            record = ds.df.loc[index].default
            # this will take some time so make sure it is running with no error
            assert record.status.value == "COMPLETE", print(record.dict())
            assert record.error is None
            assert len(record.final_energy_dict) == 24
