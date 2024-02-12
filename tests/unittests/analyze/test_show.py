from collections import namedtuple

import pytest

from cloudinit.analyze import analyze_show


@pytest.fixture
def mock_io(tmp_path):
    """Mock args for configure_io function"""
    infile = tmp_path / "infile"
    outfile = tmp_path / "outfile"
    return namedtuple("MockIO", ["infile", "outfile"])(infile, outfile)


class TestAnalyzeShow:
    """Test analyze_show (and/or helpers) in cloudinit/analyze/__init__.py"""

    def test_empty_logfile(self, mock_io, capsys):
        """Test analyze_show with an empty logfile"""
        mock_io.infile.write_text("")
        with pytest.raises(SystemExit):
            analyze_show("dontcare", mock_io)
        assert capsys.readouterr().err == f"Empty file {mock_io.infile}\n"
