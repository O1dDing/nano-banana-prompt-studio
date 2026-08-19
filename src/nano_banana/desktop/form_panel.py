"""Schema 驱动的桌面表单分组。"""

from nano_banana.desktop.components.field_group import FieldGroup


def add_schema_field_groups(window, layout) -> None:
    for category in window.prompt_schema.categories:
        group = FieldGroup(category.label, color_class=category.color_class)
        for field in category.fields:
            window._add_field(group, field.label, field.widget_key)
        window._add_category_preset_controls(group, category.id, category.label)
        layout.addWidget(group)
