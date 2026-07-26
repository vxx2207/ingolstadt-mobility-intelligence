import pandas as pd
import pytest

from ingomob.errors import SchemaError
from ingomob.schemas import TRAFFIC_COUNTS


def test_missing_column_is_rejected():
    df = pd.DataFrame({"detector_id": ["D1"], "date": ["2025-01-01"], "hour": [0]})
    with pytest.raises(SchemaError) as exc:
        TRAFFIC_COUNTS.validate(df, "unit-test")
    assert "vehicle_count" in str(exc.value)


def test_empty_table_is_rejected():
    df = pd.DataFrame(columns=["detector_id", "date", "hour", "vehicle_count"])
    with pytest.raises(SchemaError):
        TRAFFIC_COUNTS.validate(df, "unit-test")


def test_valid_frame_passes():
    df = pd.DataFrame({"detector_id": ["D1"], "date": ["2025-01-01"], "hour": [0],
                       "vehicle_count": [10]})
    TRAFFIC_COUNTS.validate(df, "unit-test")
