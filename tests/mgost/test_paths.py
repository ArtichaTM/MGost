from pathlib import Path

import pytest

from mgost.mgost.paths import External, classify
from tests.harness import FOREIGN


@pytest.mark.parametrize(
    'written, expected',
    [
        ('main.md', Path('main.md')),
        ('images/a.png', Path('images/a.png')),
        ('images/../a.png', Path('a.png')),
    ],
    ids=['flat', 'nested', 'normalised'],
)
def test_ordinary_is_root_relative(tmp_path, written, expected):
    assert classify(tmp_path, written) == expected


def test_climbing_out_is_external(tmp_path):
    root = tmp_path / 'project'

    assert classify(root, '../shared/a.png') == External(
        '../shared/a.png', tmp_path / 'shared' / 'a.png'
    )


def test_absolute_is_external_even_inside_the_root(tmp_path):
    written = str(tmp_path / 'a.png')

    assert classify(tmp_path, written) == External(
        written, tmp_path / 'a.png'
    )


def test_foreign_absolute_has_no_local_file(tmp_path):
    assert classify(tmp_path, FOREIGN) == External(FOREIGN, None)
