"""Coroutine versions of the calls, for browsers where Python cannot wait for
JavaScript synchronously (no WebAssembly JSPI)::

    from pge2py import aio
    psq = await aio.fromSeq(seq)
    params = await aio.check(psq, sys_ge)
    ok = await aio.validate(psq, sys_ge, seq)
    await aio.serialize(psq, "sequence.pge", params=params)
"""

from ._api import _acall, _check_plan, _from_seq_plan, _serialize_plan, _validate_plan, opts

__all__ = ["fromSeq", "opts", "check", "validate", "serialize"]


async def fromSeq(seq):  # noqa: N802
    """Coroutine version of ``pulseg.fromSeq``."""
    script, files, finish = _from_seq_plan(seq)
    return finish(*await _acall(script, files))


async def check(psq, sys_ge, PNSwt=(1, 1, 1)):  # noqa: N803
    """Coroutine version of ``pge2.check``."""
    script, files, finish = _check_plan(psq, sys_ge, PNSwt)
    return finish(*await _acall(script, files))


async def validate(psq, sys_ge, seq=None, row=None):
    """Coroutine version of ``pge2.validate``."""
    script, files, finish = _validate_plan(psq, sys_ge, seq, row)
    return finish(*await _acall(script, files))


async def serialize(psq, filename, pislquant=10, params=None):
    """Coroutine version of ``pge2.serialize``."""
    script, files, finish = _serialize_plan(psq, filename, pislquant, params)
    return finish(*await _acall(script, files))
