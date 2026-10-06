from __future__ import annotations

import ctypes
import keyword
import re
from dataclasses import dataclass

from ctypesgen.ctypedescs import CtypesSimple
from ctypesgen.ctypedescs import CtypesStruct
from ctypesgen.ctypedescs import CtypesType
from ctypesgen.ctypedescs import CtypesTypedef
from ctypesgen.descriptions import DescriptionCollection


@dataclass(frozen=True)
class Field:
    native_name: str
    annotation: str

    @property
    def name(self) -> str:
        name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", self.native_name)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()

    @property
    def value(self) -> str:
        value = f"native.{self.native_name}"
        kind = self.annotation
        condition = ""
        if kind.startswith("Optional["):
            kind = kind[len("Optional[") : -1]
            condition = f" if {value}.hasValue else None"
            value += ".value"
        if kind.endswith("Attributes"):
            value = f"{kind}.from_native({value})"
        return value + condition

    @property
    def nested(self) -> bool:
        return self.annotation.endswith(("Attributes", "Attributes]"))


def resolve(ctype: CtypesType, typedefs: dict[str, CtypesType]) -> CtypesType:
    while isinstance(ctype, CtypesTypedef):
        ctype = typedefs[ctype.name]
    return ctype


def annotation(ctype: CtypesType, typedefs: dict[str, CtypesType]) -> str:
    ctype = resolve(ctype, typedefs)
    if isinstance(ctype, CtypesSimple):
        kind = getattr(ctypes, ctype.py_string(), None)
        if kind is not None:
            value_type = type(kind().value)
            if value_type in (bool, int, float):
                return value_type.__name__
    if isinstance(ctype, CtypesStruct):
        if re.fullmatch(r"Native\w+(Difficulty|Performance)Attributes", ctype.tag):
            return ctype.tag[len("Native") :]
        members = dict(ctype.members or [])
        if list(members) == ["hasValue", "value"]:
            if annotation(members["hasValue"], typedefs) == "bool":
                return f"Optional[{annotation(members['value'], typedefs)}]"
    raise ValueError(f"Unsupported attribute type: {ctype}")


def generate_class(
    name: str,
    fields: list[Field],
    base: str = "",
    inherited=(),
    convert=False,
) -> str:
    parent = f"({base})" if base else ""
    lines = ["@dataclass", f"class {name}{parent}:"]
    own_fields = [field for field in fields if field not in inherited]
    lines.extend(f"    {field.name}: {field.annotation}" for field in own_fields)
    if not convert:
        if not own_fields:
            lines.append("    pass")
        return "\n".join(lines)
    if own_fields:
        lines.append("")
    lines.extend(
        [
            "    @classmethod",
            f"    def from_native(cls, native: bindings.Native{name}) -> {name}:",
            "        return cls(",
        ],
    )
    lines.extend(f"            {field.name}={field.value}," for field in fields)
    lines.append("        )")
    return "\n".join(lines)


def generate_attributes(descriptions: DescriptionCollection) -> str:
    typedefs = {item.name: item.ctype for item in descriptions.typedefs}
    models = {}
    for name, ctype in sorted(typedefs.items()):
        if not re.fullmatch(r"Native\w+(Difficulty|Performance)Attributes", name):
            continue
        struct = resolve(ctype, typedefs)
        if not isinstance(struct, CtypesStruct) or struct.members is None:
            raise ValueError(f"Missing attribute struct: {name}")
        fields = [Field(member, annotation(kind, typedefs)) for member, kind in struct.members]
        names = [field.name for field in fields]
        if len(names) != len(set(names)) or any(keyword.iskeyword(name) for name in names):
            raise ValueError(f"Invalid Python attribute names: {name}")
        models[name[len("Native") :]] = fields

    classes = []
    exports = []
    for category in ("Difficulty", "Performance"):
        group = {
            name: fields
            for name, fields in models.items()
            if name.endswith(category + "Attributes") and not any(field.nested for field in fields)
        }
        if not group:
            raise ValueError(f"No native {category.lower()} attribute exports")
        base = category + "Attributes"
        first = next(iter(group.values()))
        common = [field for field in first if all(field in fields for fields in group.values())]
        classes.append(generate_class(base, common))
        exports.append(base)
        for name, fields in group.items():
            classes.append(generate_class(name, fields, base, common, convert=True))
            exports.append(name)

    for name, fields in models.items():
        if name not in exports:
            classes.append(generate_class(name, fields, convert=True))
            exports.append(name)

    imports = [
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "from typing import Optional",
        "",
        "from . import bindings",
        "",
        f"__all__ = {exports!r}",
    ]
    return "\n".join(imports) + "\n\n\n" + "\n\n\n".join(classes) + "\n"
