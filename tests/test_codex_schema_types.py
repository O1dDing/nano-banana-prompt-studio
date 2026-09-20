from nano_banana.core.schema import get_schema
from nano_banana.core.codex_schema import prompt_output_schema


def test_actual_project_field_types_match_output_schema():
    output = prompt_output_schema()
    arrays = 0
    for field in get_schema().iter_fields():
        node = output
        for name in field.path:
            node = node['properties'][name]
        expected = 'array' if field.type == 'string_list' else field.type
        assert node['type'] == expected, field.path
        if expected == 'array':
            arrays += 1
            assert node['items'] == {'type': 'string'}
    assert arrays > 0
