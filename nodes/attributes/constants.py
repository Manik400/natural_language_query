from enum import IntEnum


class AttributeValueType(IntEnum):
    string = 0
    number = 1
    boolean = 2


class Operators(IntEnum):
    EQUAL = 0
    NOTEQUAL = 1
    GREATERTHAN = 2
    SMALLERTHAN = 3
    GREATERTHANOREQUAL = 4
    SMALLERTHANOREQUAL = 5
    CONTAINS = 6
    NOTCONTAINS = 7
    WASUPDATED = 8
    IN = 9
    NOTIN = 10
    BETWEEN = 11
    LIKE = 12
    NOTLIKE = 13
    ANY = 14
    ALL = 15


class ConditionType(IntEnum):
    ANY = 14
    ALL = 15


MULTI_VALUE_OPERATORS = {
    Operators.IN,
    Operators.NOTIN,
    Operators.BETWEEN,
    Operators.ANY,
    Operators.ALL,
}

OPERATOR_RULES: dict = {
    Operators.EQUAL: {
        "allowed_types": [
            AttributeValueType.string,
            AttributeValueType.number,
            AttributeValueType.boolean,
        ],
        "value_type": "scalar",
    },
    Operators.NOTEQUAL: {
        "allowed_types": [
            AttributeValueType.string,
            AttributeValueType.number,
            AttributeValueType.boolean,
        ],
        "value_type": "scalar",
    },
    Operators.GREATERTHAN: {
        "allowed_types": [AttributeValueType.number],
        "value_type": "scalar",
    },
    Operators.SMALLERTHAN: {
        "allowed_types": [AttributeValueType.number],
        "value_type": "scalar",
    },
    Operators.GREATERTHANOREQUAL: {
        "allowed_types": [AttributeValueType.number],
        "value_type": "scalar",
    },
    Operators.SMALLERTHANOREQUAL: {
        "allowed_types": [AttributeValueType.number],
        "value_type": "scalar",
    },
    Operators.CONTAINS: {
        "allowed_types": [AttributeValueType.string],
        "value_type": "scalar",
    },
    Operators.NOTCONTAINS: {
        "allowed_types": [AttributeValueType.string],
        "value_type": "scalar",
    },
    Operators.LIKE: {
        "allowed_types": [AttributeValueType.string],
        "value_type": "scalar",
    },
    Operators.NOTLIKE: {
        "allowed_types": [AttributeValueType.string],
        "value_type": "scalar",
    },
    Operators.WASUPDATED: {
        "allowed_types": [
            AttributeValueType.string,
            AttributeValueType.number,
            AttributeValueType.boolean,
        ],
        "value_type": "none",
    },
    Operators.IN: {
        "allowed_types": [AttributeValueType.string, AttributeValueType.number],
        "value_type": "list",
    },
    Operators.NOTIN: {
        "allowed_types": [AttributeValueType.string, AttributeValueType.number],
        "value_type": "list",
    },
    Operators.ANY: {
        "allowed_types": [AttributeValueType.string, AttributeValueType.number],
        "value_type": "list",
    },
    Operators.ALL: {
        "allowed_types": [AttributeValueType.string, AttributeValueType.number],
        "value_type": "list",
    },
    Operators.BETWEEN: {
        "allowed_types": [AttributeValueType.number, AttributeValueType.string],
        "value_type": "range",
    },
}
