"""The check chain through the desktop backend (GNU Octave via oct2py)."""

import shutil

import numpy as np
import pypulseq as pp
import pytest

import pge2py

pytestmark = pytest.mark.skipif(not shutil.which("octave-cli") and not shutil.which("octave"),
                                reason="GNU Octave not installed")

GE_SYSTEM = dict(
    max_grad=50 / np.sqrt(3), grad_unit="mT/m", max_slew=120 / np.sqrt(3), slew_unit="T/m/s",
    rf_dead_time=0, rf_ringdown_time=0, adc_dead_time=0,
    rf_raster_time=2e-6, adc_raster_time=2e-6, grad_raster_time=4e-6, block_duration_raster=4e-6,
)


def gre(system, n=32, n_dummy=4, pislquant=2):
    """Small 2D GRE: dummy, receive-gain and imaging TRs, one TRID each."""
    rf, gz, _ = pp.make_sinc_pulse(np.deg2rad(10), duration=2e-3, slice_thickness=5e-3,
                                   time_bw_product=4, system=system, return_gz=True, use="excitation")
    gz_reph = pp.make_trapezoid("z", area=-gz.area / 2, duration=1e-3, system=system)
    dk = 1 / 240e-3
    gx = pp.make_trapezoid("x", flat_area=n * dk, flat_time=n * 20e-6, system=system)
    adc = pp.make_adc(n, duration=gx.flat_time, delay=gx.rise_time, system=system)
    gx_pre = pp.make_trapezoid("x", area=-gx.area / 2, duration=1e-3, system=system)
    pe = (np.arange(n) - n / 2) * dk
    gy = pp.make_trapezoid("y", area=np.max(np.abs(pe)), duration=1e-3, system=system)
    trid = [pp.make_label(type="SET", label="TRID", value=v) for v in (1, 2, 3)]
    seq = pp.Sequence(system)
    for iy in range(-n_dummy - pislquant, n):
        k = 0 if iy < -pislquant else 1 if iy < 0 else 2
        s = pe[iy] / gy.area if iy >= 0 else 0.0
        seq.add_block(rf, gz, trid[k])
        seq.add_block(gx_pre, pp.scale_grad(gy, s), gz_reph)
        seq.add_block(gx) if k == 0 else seq.add_block(gx, adc)
        seq.add_block(pp.scale_grad(gy, -s), pp.make_delay(2e-3))
    return seq


@pytest.fixture(scope="module")
def ge():
    return pge2py.GE()


def test_chain(ge, tmp_path):
    report = ge.from_seq(gre(pp.Opts(**GE_SYSTEM)))
    assert [s.trid for s in report.segments] == [1, 2, 3]
    assert [s.n_instances for s in report.segments] == [4, 2, 32]
    assert [s.layout for s in report.segments] == ["ABCD", "ABED", "ABED"]
    params = ge.check()
    assert set(params) == {"b1max", "gmax", "smax"} and params["b1max"] > 0
    assert ge.validate()
    pge = ge.serialize(tmp_path / "gre.pge", pislquant=2)
    assert pge.stat().st_size > 0


def test_wrong_raster_is_rejected(ge):
    system = pp.Opts(**{**GE_SYSTEM, "rf_raster_time": 1e-6, "adc_raster_time": 1e-7,
                        "grad_raster_time": 10e-6, "block_duration_raster": 10e-6})
    ge.from_seq(gre(system))
    with pytest.raises(pge2py.PGE2Error, match="RF_UPDATE_TIME"):
        ge.check()


def test_missing_trid_is_rejected(ge):
    seq = pp.Sequence()
    seq.add_block(pp.make_delay(1e-3))
    with pytest.raises(pge2py.PGE2Error, match="TRID"):
        ge.from_seq(seq)
