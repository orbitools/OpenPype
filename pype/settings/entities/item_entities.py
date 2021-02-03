import copy
from abc import abstractmethod

from .lib import (
    NOT_SET,
    DefaultsNotDefined
)
from .constants import (
    OverrideState,
    WRAPPER_TYPES,
    METADATA_KEYS,
    M_OVERRIDEN_KEY,
    M_ENVIRONMENT_KEY,
    M_DYNAMIC_KEY_LABEL
)
from .base_entity import BaseEntity

"""
# TODO
Methods:
- save

# Properties
## Value attributes - should be set on `set_override_state` based on updated
    values
has_defaults
has_studio_override
had_studio_override
has_project_override
had_project_override

# Abstract properties:
## Value of an item no matter if has any overrides (without metadata)
value

## Schema types from schemas
schema_types

## Unsaved changes
has_unsaved_changes
child_is_modified

child_has_studio_override
child_has_project_override

# Abstract methods:
## Trigger update of current values(discard changes) and reseting modifications
set_override_state

## Change current value and trigger modifications and validations of values
- is not for internal value update
set_value

## Return value which will be stored to overrides with metadata
settings_value

## Update values of defaults, studio overrides and project overrides
- these should be used anytime to update values
- current value should be updated if item is without modifications
update_default_value
update_studio_values
update_project_values

## Item should be able register change callbacks
on_change

## children should notify parent that something has changed
- value has changed
- was set to overriden
- current value has changed
- etc.
on_child_change

## Save settings
save

## Action calls - last to implement
discard_changes
set_studio_default
reset_to_pype_default
remove_overrides
set_as_overriden
"""


class ItemEntity(BaseEntity):
    def __init__(self, schema_data, parent, is_dynamic_item=False):
        super(ItemEntity, self).__init__(schema_data, parent, is_dynamic_item)

        self.create_schema_object = self.parent.create_schema_object

        self.is_file = schema_data.get("is_file", False)
        self.is_group = schema_data.get("is_group", False)
        self.is_in_dynamic_item = bool(
            not is_dynamic_item
            and (parent.is_dynamic_item or parent.is_in_dynamic_item)
        )

        # Root item reference
        self.root_item = self.parent.root_item

        # File item reference
        if self.parent.is_file:
            self.file_item = self.parent
        elif self.parent.file_item:
            self.file_item = self.parent.file_item

        # Group item reference
        if self.parent.is_group:
            self.group_item = self.parent
        elif self.parent.group_item:
            self.group_item = self.parent.group_item

        # Dynamic item can't have key defined in it-self
        # - key is defined by it's parent
        if self.is_dynamic_item:
            self.require_key = False

        # If value should be stored to environments
        self.env_group_key = schema_data.get("env_group_key")
        self.is_env_group = bool(self.env_group_key is not None)

        roles = schema_data.get("roles")
        if roles is None:
            roles = parent.roles
        elif not isinstance(roles, list):
            roles = [roles]
        self.roles = roles

        # States of inputs
        # QUESTION has usage in entity?
        self.state = None

        self.key = schema_data.get("key")
        self.label = schema_data.get("label")

        self.item_initalization()

    def schema_validations(self):
        if self.valid_value_types is NOT_SET:
            raise ValueError("Attribute `valid_value_types` is not filled.")

        if self.require_key and not self.key:
            error_msg = "{}: Missing \"key\" in schema data. {}".format(
                self.path, str(self.schema_data).replace("'", '"')
            )
            raise KeyError(error_msg)

        if not self.label and self.is_group:
            raise ValueError(
                "{}: Item is set as `is_group` but has empty `label`.".format(
                    self.path
                )
            )

        if self.is_group and self.group_item:
            raise ValueError("{}: Group item in group item".format(self.path))

        if not self.file_item and self.is_env_group:
            raise ValueError((
                "{}: Environment item is not inside file"
                " item so can't store metadata for defaults."
            ).format(self.path))

        if self.label and self.is_dynamic_item:
            raise ValueError((
                "{}: Item has set label but is used as dynamic item."
            ).format(self.path))

    @abstractmethod
    def item_initalization(self):
        pass

    def save(self):
        """Call save on root item."""
        self.root_item.save()


class GUIEntity(ItemEntity):
    gui_type = True

    schema_types = ["divider", "splitter", "label"]
    child_has_studio_override = False
    has_unsaved_changes = False
    child_is_modified = False
    child_has_project_override = False
    value = NOT_SET

    path = "GUIEntity"

    # Abstract methods
    get_child_path = None
    set_value = None
    set_override_state = None
    discard_changes = None
    on_change = None
    on_child_change = None
    on_value_change = None
    settings_value = None
    remove_overrides = None
    reset_to_pype_default = None
    set_as_overriden = None
    set_studio_default = None
    update_default_value = None
    update_studio_values = None
    update_project_values = None

    def __getitem__(self, key):
        return self.schema_data[key]

    def schema_validations(self):
        return

    def item_initalization(self):
        self.valid_value_types = tuple()
        self.require_key = False


class DictImmutableKeysEntity(ItemEntity):
    schema_types = ["dict"]

    def __getitem__(self, key):
        return self.non_gui_children[key]

    def __setitem__(self, key, value):
        child_obj = self.non_gui_children[key]
        child_obj.set_value(value)

    def __iter__(self):
        for key in self.keys():
            yield key

    def get(self, key, default=None):
        return self.non_gui_children.get(key, default)

    def keys(self):
        return self.non_gui_children.keys()

    def values(self):
        return self.non_gui_children.values()

    def items(self):
        return self.non_gui_children.items()

    def on_value_change(self):
        raise NotImplementedError(
            "{} - on_value_change".format(self.__class__.__name__)
        )

    def schema_validations(self):
        if self.checkbox_key:
            checkbox_child = self.non_gui_children.get(self.checkbox_key)
            if not checkbox_child:
                raise ValueError(
                    "{}: Checkbox children \"{}\" was not found.".format(
                        self.path, self.checkbox_key
                    )
                )
            from .input_entities import BoolEntity
            if not isinstance(checkbox_child, BoolEntity):
                raise TypeError((
                    "{}: Checkbox children \"{}\" is not `boolean` type."
                ).format(self.path, self.checkbox_key))

        super(DictImmutableKeysEntity, self).schema_validations()
        for child_obj in self.children:
            child_obj.schema_validations()

    def on_change(self):
        self.update_current_metadata()
        for callback in self.on_change_callbacks:
            callback()
        self.parent.on_child_change(self)

    def on_child_change(self, _child_obj):
        self.on_change()

    def _add_children(self, schema_data, first=True):
        added_children = []
        for children_schema in schema_data["children"]:
            if children_schema["type"] in WRAPPER_TYPES:
                _children_schema = copy.deepcopy(children_schema)
                wrapper_children = self._add_children(
                    children_schema
                )
                _children_schema["children"] = wrapper_children
                added_children.append(_children_schema)
                continue

            child_obj = self.create_schema_object(children_schema, self)
            self.children.append(child_obj)
            added_children.append(child_obj)
            if isinstance(child_obj, GUIEntity):
                continue

            if child_obj.key in self.non_gui_children:
                raise KeyError("Duplicated key \"{}\"".format(child_obj.key))
            self.non_gui_children[child_obj.key] = child_obj

        if not first:
            return added_children

        for child_obj in added_children:
            if isinstance(child_obj, BaseEntity):
                continue
            self.gui_wrappers.append(child_obj)

    def item_initalization(self):
        self.default_metadata = NOT_SET
        self.studio_override_metadata = NOT_SET
        self.project_override_metadata = NOT_SET

        # `current_metadata` are still when schema is loaded
        # - only metadata stored with dict item are gorup overrides in
        #   M_OVERRIDEN_KEY
        self.current_metadata = {}
        self.metadata_are_modified = False

        # Children are stored by key as keys are immutable and are defined by
        # schema
        self.valid_value_types = (dict, )
        self.children = []
        self.non_gui_children = {}
        self.gui_wrappers = []
        self._add_children(self.schema_data)

        if self.is_dynamic_item:
            self.require_key = False

        # GUI attributes
        self.checkbox_key = self.schema_data.get("checkbox_key")
        self.highlight_content = self.schema_data.get(
            "highlight_content", False
        )
        self.show_borders = self.schema_data.get("show_borders", True)
        self.collapsible = self.schema_data.get("collapsable", True)
        self.collapsed = self.schema_data.get("collapsed", True)

        # Not yet implemented
        self.use_label_wrap = self.schema_data.get("use_label_wrap") or True

    def get_child_path(self, child_obj):
        result_key = None
        for key, _child_obj in self.non_gui_children.items():
            if _child_obj is child_obj:
                result_key = key
                break

        if result_key is None:
            raise ValueError("Didn't found child {}".format(child_obj))

        return "/".join([self.path, result_key])

    def set_value(self, value):
        for _key, _value in value.items():
            self.non_gui_children[_key].set_value(_value)

    def update_current_metadata(self):
        # Define if current metadata are
        metadata = NOT_SET
        if self.override_state is OverrideState.PROJECT:
            # metadata are NOT_SET if project overrides do not override this
            # item
            metadata = self.project_override_metadata

        if self.override_state is OverrideState.STUDIO or metadata is NOT_SET:
            metadata = self.studio_override_metadata

        current_metadata = {}
        for key, child_obj in self.non_gui_children.items():
            if not child_obj.is_group:
                continue

            if (
                self.override_state is OverrideState.STUDIO
                and not child_obj.has_studio_override
            ):
                continue

            if (
                self.override_state is OverrideState.PROJECT
                and not child_obj.has_project_override
            ):
                continue

            if M_OVERRIDEN_KEY not in current_metadata:
                current_metadata[M_OVERRIDEN_KEY] = []
            current_metadata[M_OVERRIDEN_KEY].append(key)

        if metadata is NOT_SET and not current_metadata:
            self.metadata_are_modified = False
        else:
            self.metadata_are_modified = current_metadata != metadata
        self.current_metadata = current_metadata

    def set_override_state(self, state):
        # Change has/had override states
        self.override_state = state
        if state is OverrideState.NOT_DEFINED:
            pass

        elif state is OverrideState.DEFAULTS:
            self.has_default_value = self.default_value is not NOT_SET

        elif state is OverrideState.STUDIO:
            if self.studio_override_metadata is NOT_SET:
                self.had_studio_override = False
            self.has_studio_override = self.had_studio_override

        elif state is OverrideState.PROJECT:
            if self.project_override_metadata is NOT_SET:
                self.had_project_override = False
            self._has_project_override = self.had_project_override

        for child_obj in self.non_gui_children.values():
            child_obj.set_override_state(state)

        self.update_current_metadata()

    @property
    def value(self):
        output = {}
        for key, child_obj in self.non_gui_children.items():
            output[key] = child_obj.value
        return output

    @property
    def has_unsaved_changes(self):
        if self.metadata_are_modified:
            return True

        if (
            self.override_state is OverrideState.PROJECT
            and self._has_project_override != self.had_project_override
        ):
            return True

        elif (
            self.override_state is OverrideState.STUDIO
            and self.has_studio_override != self.had_studio_override
        ):
            return True

        return self.child_is_modified

    @property
    def child_is_modified(self):
        for child_obj in self.non_gui_children.values():
            if child_obj.has_unsaved_changes:
                return True
        return False

    @property
    def child_has_studio_override(self):
        for child_obj in self.non_gui_children.values():
            if child_obj.child_has_studio_override:
                return True
        return False

    @property
    def child_has_project_override(self):
        if self.override_state is OverrideState.PROJECT:
            for child_obj in self.non_gui_children.values():
                if child_obj.child_has_studio_override:
                    return True
        return False

    def settings_value(self):
        if self.override_state is OverrideState.NOT_DEFINED:
            return NOT_SET

        if self.is_group:
            if self.override_state is OverrideState.STUDIO:
                if not self.has_studio_override:
                    return NOT_SET
            elif self.override_state is OverrideState.PROJECT:
                if not self._has_project_override:
                    return NOT_SET

        output = {}
        for key, child_obj in self.non_gui_children.items():
            value = child_obj.settings_value()
            if value is not NOT_SET:
                output[key] = value

        if self.override_state is OverrideState.DEFAULTS:
            return output

        if not output:
            return NOT_SET

        output.update(self.current_metadata)
        return output

    def _prepare_value(self, value):
        if value is NOT_SET:
            return NOT_SET, NOT_SET

        metadata = {}
        for key in METADATA_KEYS:
            if key in value:
                metadata[key] = value.pop(key)
        return value, metadata

    def update_default_value(self, value):
        self.has_default_value = value is not NOT_SET
        # TODO add value validation
        value, metadata = self._prepare_value(value)
        self.default_metadata = metadata

        if value is NOT_SET:
            for child_obj in self.non_gui_children.values():
                child_obj.update_default_value(value)
            return

        for _key, _value in value.items():
            child_obj = self.non_gui_children.get(_key)
            if child_obj:
                child_obj.update_default_value(_value)
            else:
                # TODO store that has unsaved changes if is group item or
                # is inside group item
                self.log.warning(
                    "Unknown key in default values \"{}\"".format(_key)
                )

    def update_studio_values(self, value):
        value, metadata = self._prepare_value(value)
        self.studio_override_metadata = metadata

        if value is NOT_SET:
            for child_obj in self.non_gui_children.values():
                child_obj.update_studio_values(value)
            return

        for _key, _value in value.items():
            child_obj = self.non_gui_children.get(_key)
            if child_obj:
                child_obj.update_studio_values(_value)
            else:
                # TODO store that has unsaved changes if is group item or
                # is inside group item
                self.log.warning(
                    "Unknown key in studio overrides \"{}\"".format(_key)
                )

    def update_project_values(self, value):
        value, metadata = self._prepare_value(value)
        self.project_override_metadata = metadata

        if value is NOT_SET:
            for child_obj in self.non_gui_children.values():
                child_obj.update_project_values(value)
            return

        for _key, _value in value.items():
            child_obj = self.non_gui_children.get(_key)
            if child_obj:
                child_obj.update_project_values(_value)
            else:
                # TODO store that has unsaved changes if is group item or
                # is inside group item
                self.log.warning(
                    "Unknown key in project overrides \"{}\"".format(_key)
                )

    def discard_changes(self):
        pass

    def remove_overrides(self):
        pass

    def reset_to_pype_default(self):
        pass

    def set_as_overriden(self):
        pass

    def set_studio_default(self):
        pass


class DictMutableKeysEntity(ItemEntity):
    schema_types = ["dict-modifiable"]
    _miss_arg = object()

    def __getitem__(self, key):
        return self.children_by_key[key]

    def __setitem__(self, key, value):
        self.set_value_for_key(key, value)

    def __iter__(self):
        for key in self.keys():
            yield key

    def pop(self, key, default=_miss_arg):
        if key not in self.children_by_key:
            if default is self._miss_arg:
                raise KeyError("Key \"{}\" not found.".format(key))
            return default

        child_obj = self.children_by_key.pop(key)
        self.children.remove(child_obj)
        self.on_value_change()
        return child_obj

    def get(self, key, default=None):
        return self.children_by_key.get(key, default)

    def keys(self):
        return self.children_by_key.keys()

    def values(self):
        return self.children_by_key.values()

    def items(self):
        return self.children_by_key.items()

    def clear(self):
        for key in tuple(self.children_by_key.keys()):
            self.pop(key)

    def change_key(self, old_key, new_key):
        if new_key == old_key:
            return
        self.children_by_key[new_key] = self.children_by_key.pop(old_key)

    def change_child_key(self, child_entity, new_key):
        old_key = None
        for key, child in self.children_by_key.items():
            if child is child_entity:
                old_key = key
                break

        self.change_key(old_key, new_key)

    def get_child_key(self, child_entity):
        for key, child in self.children_by_key.items():
            if child is child_entity:
                return key
        return None

    def add_new_key(self, key):
        new_child = self.create_schema_object(self.item_schema, self, True)
        self.children.append(new_child)
        self.children_by_key[key] = new_child
        return new_child

    def item_initalization(self):
        self.default_metadata = {}
        self.studio_override_metadata = {}
        self.project_override_metadata = {}

        # current_metadata are still when schema is loaded
        self.current_metadata = {}

        self.valid_value_types = (dict, )
        self.value_on_not_set = {}

        self.children = []
        self.children_by_key = {}
        self._current_value = NOT_SET

        self.value_is_env_group = (
            self.schema_data.get("value_is_env_group") or False
        )
        self.required_keys = self.schema_data.get("required_keys") or []
        self.collapsible_key = self.schema_data.get("collapsable_key") or False
        # GUI attributes
        self.hightlight_content = (
            self.schema_data.get("highlight_content") or False
        )
        self.collapsible = self.schema_data.get("collapsable", False)
        self.collapsed = self.schema_data.get("collapsed", True)

        object_type = self.schema_data["object_type"]
        if not isinstance(object_type, dict):
            # Backwards compatibility
            object_type = {
                "type": object_type
            }
            input_modifiers = self.schema_data.get("input_modifiers") or {}
            if input_modifiers:
                self.log.warning((
                    "Used deprecated key `input_modifiers` to define item."
                    " Rather use `object_type` as dictionary with modifiers."
                ))
                object_type.update(input_modifiers)
        self.item_schema = object_type

        if self.value_is_env_group:
            self.item_schema["env_group_key"] = ""

        if not self.group_item:
            self.is_group = True

    def schema_validations(self):
        super(DictMutableKeysEntity, self).schema_validations()

        # TODO Ability to store labels should be defined with different key
        if self.collapsible_key and not self.file_item:
            raise ValueError((
                "{}: Modifiable dictionary with collapsible keys is not under"
                " file item so can't store metadata."
            ).format(self.path))

        for child_obj in self.children:
            child_obj.schema_validations()

    def get_child_path(self, child_obj):
        result_key = None
        for key, _child_obj in self.children_by_key.items():
            if _child_obj is child_obj:
                result_key = key
                break

        if result_key is None:
            raise ValueError("Didn't found child {}".format(child_obj))

        return "/".join([self.path, result_key])

    def set_value_for_key(self, key, value, batch=False):
        # TODO Check for value type if is Settings entity?
        child_obj = self.children_by_key.get(key)
        if not child_obj:
            child_obj = self.add_new_key(key)

        child_obj.set_value(value)

        if not batch:
            self.on_value_change()

    def on_change(self):
        # TODO implement
        pass

    def on_child_change(self, child_obj):
        # TODO implement
        print("{} on_child_change not yet implemented".format(
            self.__class__.__name__
        ))

    def _metadata_for_current_state(self):
        if (
            self.override_state is OverrideState.PROJECT
            and self.project_override_value is not NOT_SET
        ):
            previous_metadata = self.project_override_value

        elif self.studio_override_value is not NOT_SET:
            previous_metadata = self.studio_override_metadata
        else:
            previous_metadata = self.default_metadata
        return copy.deepcopy(previous_metadata)

    def get_metadata_from_value(self, value, previous_metadata=None):
        """Get metada for entered value.

        Method may modify entered value object in case that contain .
        """
        metadata = {}
        if not isinstance(value, dict):
            return metadata

        # Fill label metadata
        # - first check if value contain them
        if M_DYNAMIC_KEY_LABEL in value:
            metadata[M_DYNAMIC_KEY_LABEL] = value.pop(M_DYNAMIC_KEY_LABEL)

        # - check if metadata for current state contain metadata
        elif M_DYNAMIC_KEY_LABEL in previous_metadata:
            # Get previous metadata fo current state if were not entered
            if previous_metadata is None:
                previous_metadata = self._metadata_for_current_state()
            # Create copy to not affect data passed with arguments
            label_metadata = copy.deepcopy(
                previous_metadata[M_DYNAMIC_KEY_LABEL]
            )
            for key in tuple(label_metadata.keys()):
                if key not in value:
                    label_metadata.pop(key)

            metadata[M_DYNAMIC_KEY_LABEL] = label_metadata

        # Pop all other metadata keys from value
        for key in METADATA_KEYS:
            if key in value:
                value.pop(key)

        # Add environment metadata
        if self.is_env_group:
            metadata[M_ENVIRONMENT_KEY] = {
                self.env_group_key: list(value.keys())
            }
        return metadata

    def set_value(self, value):
        for _key, _value in value.items():
            self.set_value_for_key(_key, _value, True)
        self.on_value_change()

    def on_value_change(self):
        raise NotImplementedError(self.__class__.__name__)

    def set_override_state(self, state):
        # TODO change metadata
        self.override_state = state
        if (
            not self.has_default_value
            and state in (OverrideState.STUDIO, OverrideState.PROJECT)
        ):
            raise DefaultsNotDefined(self)

        using_overrides = True
        if (
            state is OverrideState.PROJECT
            and self.project_override_value is not NOT_SET
        ):
            value = self.project_override_value
            metadata = self.project_override_metadata

        elif self.studio_override_value is not NOT_SET:
            value = self.studio_override_value
            metadata = self.studio_override_metadata

        else:
            using_overrides = False
            value = self.default_value
            metadata = self.default_metadata

        # TODO REQUIREMENT value must be stored to _current_value
        # - current value must not be dynamic!!!
        # - it is required to update metadata on the fly
        if value is NOT_SET:
            value = self.value_on_not_set

        new_value = copy.deepcopy(value)
        self._current_value = new_value
        # It is important to pass `new_value`!!!
        self.current_metadata = self.get_metadata_from_value(
            new_value, metadata
        )

        # Simulate `clear` method without triggering value change
        for key in tuple(self.children_by_key.keys()):
            child_obj = self.children_by_key.pop(key)
            self.children.remove(child_obj)

        # Create new children
        for _key, _value in self._current_value.items():
            child_obj = self.add_new_key(_key)
            child_obj.update_default_value(_value)
            if using_overrides:
                if state is OverrideState.STUDIO:
                    child_obj.update_studio_values(value)
                else:
                    child_obj.update_project_values(value)

            child_obj.set_override_state(state)

    @property
    def value(self):
        return self._current_value

    @property
    def has_unsaved_changes(self):
        pass

    @property
    def child_has_studio_override(self):
        pass

    @property
    def child_is_modified(self):
        pass

    @property
    def child_has_project_override(self):
        if self.override_state is OverrideState.PROJECT:
            # TODO implement
            pass
        return False

    def discard_changes(self):
        pass

    def settings_value(self):
        if self.override_state is OverrideState.NOT_DEFINED:
            return NOT_SET

        if self.is_group:
            if self.override_state is OverrideState.STUDIO:
                if not self.has_studio_override:
                    return NOT_SET

            elif self.override_state is OverrideState.PROJECT:
                if not self._has_project_override:
                    return NOT_SET

        output = copy.deepcopy(self._current_value)
        output.update(copy.deepcopy(self.current_metadata))
        return output

    def remove_overrides(self):
        pass

    def reset_to_pype_default(self):
        pass

    def set_as_overriden(self):
        pass

    def set_studio_default(self):
        pass

    def _prepare_value(self, value):
        metadata = {}
        if isinstance(value, dict):
            for key in METADATA_KEYS:
                if key in value:
                    metadata[key] = value.pop(key)
        return value, metadata

    def update_default_value(self, value):
        self.has_default_value = value is not NOT_SET
        value, metadata = self._prepare_value(value)
        self.default_value = value
        self.default_metadata = metadata

    def update_studio_values(self, value):
        value, metadata = self._prepare_value(value)
        self.project_override_value = value
        self.studio_override_metadata = metadata

    def update_project_values(self, value):
        value, metadata = self._prepare_value(value)
        self.studio_override_value = value
        self.project_override_metadata = metadata


class ListEntity(ItemEntity):
    schema_types = ["list"]

    def __iter__(self):
        for item in self.children:
            yield item

    def append(self, item):
        child_obj = self.add_new_item()
        child_obj.set_value(item)
        self.on_change()

    def extend(self, items):
        for item in items:
            self.append(item)

    def clear(self):
        self.children.clear()
        self.on_change()

    def pop(self, idx):
        self.children.pop(idx)
        self.on_change()

    def remove(self, item):
        for idx, child_obj in enumerate(self.children):
            if child_obj.value == item:
                self.pop(idx)
                return
        raise ValueError("ListEntity.remove(x): x not in ListEntity")

    def insert(self, idx, item):
        child_obj = self.add_new_item(idx)
        child_obj.set_value(item)
        self.on_change()

    def add_new_item(self, idx=None):
        child_obj = self.create_schema_object(self.item_schema, self, True)
        child_obj.set_override_state(self.override_state)
        if idx is None:
            self.children.append(child_obj)
        else:
            self.children.insert(idx, child_obj)
        return child_obj

    def item_initalization(self):
        self.valid_value_types = (list, )
        self.children = []

        item_schema = self.schema_data["object_type"]
        if not isinstance(item_schema, dict):
            item_schema = {"type": item_schema}
        self.item_schema = item_schema

        if not self.group_item:
            self.is_group = True

        # GUI attributes
        self.use_label_wrap = self.schema_data.get("use_label_wrap") or False
        # Used only if `use_label_wrap` is set to True
        self.collapsible = self.schema_data.get("collapsible") or True
        self.collapsed = self.schema_data.get("collapsed") or False

    def schema_validations(self):
        super(ListEntity, self).schema_validations()

        if self.is_dynamic_item and self.use_label_wrap:
            raise ValueError(
                "`ListWidget` can't have set `use_label_wrap` to True and"
                " be used as widget at the same time."
            )

        if self.use_label_wrap and not self.label:
            raise ValueError(
                "`ListWidget` can't have set `use_label_wrap` to True and"
                " not have set \"label\" key at the same time."
            )

        for child_obj in self.children:
            child_obj.schema_validations()

    def get_child_path(self, child_obj):
        result_idx = None
        for idx, _child_obj in enumerate(self.children):
            if _child_obj is child_obj:
                result_idx = idx
                break

        if result_idx is None:
            raise ValueError("Didn't found child {}".format(child_obj))

        return "/".join([self.path, str(result_idx)])

    def set_value(self, value):
        pass

    def on_change(self):
        pass

    def on_child_change(self, child_obj):
        print("{} - on_child_change".format(self.__class__.__name__))

    def on_value_change(self):
        raise NotImplementedError(self.__class__.__name__)

    def set_override_state(self, state):
        self.override_state = state
        if (
            not self.has_default_value
            and state in (OverrideState.STUDIO, OverrideState.PROJECT)
        ):
            raise DefaultsNotDefined(self)

        self._set_value()

    def _set_value(self, value=NOT_SET):
        while self.children:
            self.children.pop(0)

        if self.override_state is OverrideState.NOT_DEFINED:
            return

        if value is NOT_SET:
            if self.override_state is OverrideState.PROJECT:
                if self.had_project_override:
                    value = self.project_override_value
                elif self.had_studio_override:
                    value = self.studio_override_value
                else:
                    value = self.default_value

            elif self.override_state is OverrideState.STUDIO:
                if self.had_studio_override:
                    value = self.studio_override_value
                else:
                    value = self.default_value

            elif self.override_state is OverrideState.DEFAULTS:
                value = self.default_value

            if value is NOT_SET:
                value = self.value_on_not_set

        for item in value:
            child_obj = self.create_schema_object(self.item_schema, self, True)
            self.children.append(child_obj)
            child_obj.update_default_value(item)
            if self.override_state is OverrideState.STUDIO:
                if self.had_studio_override:
                    child_obj.update_studio_values(item)

            elif self.override_state is OverrideState.PROJECT:
                if self.had_project_override:
                    child_obj.update_project_values(item)

        for child_obj in self.children:
            child_obj.set_override_state(self.override_state)

    @property
    def value(self):
        output = []
        for child_obj in self.children:
            output.append(child_obj.value)
        return output

    @property
    def child_has_studio_override(self):
        pass

    @property
    def has_unsaved_changes(self):
        pass

    @property
    def child_is_modified(self):
        pass

    @property
    def child_has_project_override(self):
        if self.override_state is OverrideState.PROJECT:
            # TODO implement
            pass
        return False

    def discard_changes(self):
        pass

    def settings_value(self):
        if self.override_state is OverrideState.NOT_DEFINED:
            return NOT_SET

        if self.is_group:
            if self.override_state is OverrideState.STUDIO:
                if not self.has_studio_override:
                    return NOT_SET
            elif self.override_state is OverrideState.PROJECT:
                if not self._has_project_override:
                    return NOT_SET

        output = []
        for child_obj in self.children:
            output.append(child_obj.settings_value())
        return output

    def remove_overrides(self):
        pass

    def reset_to_pype_default(self):
        pass

    def set_as_overriden(self):
        pass

    def set_studio_default(self):
        pass

    def update_default_value(self, value):
        self.has_default_value = value is not NOT_SET
        self.default_value = value

    def update_studio_values(self, value):
        self.studio_override_value = value

    def update_project_values(self, value):
        self.project_override_value = value


class PathEntity(ItemEntity):
    schema_types = ["path-widget"]
    platforms = ("windows", "darwin", "linux")
    platform_labels_mapping = {
        "windows": "Windows",
        "darwin": "MacOS",
        "linux": "Linux"
    }
    path_item_type_error = "Got invalid path value type {}. Expected: {}"
    attribute_error_msg = (
        "'PathEntity' has no attribute '{}' if is not set as multiplatform"
    )

    def __setitem__(self, *args, **kwargs):
        return self.child_obj.__setitem__(*args, **kwargs)

    def __getitem__(self, *args, **kwargs):
        return self.child_obj.__getitem__(*args, **kwargs)

    def __iter__(self):
        return self.child_obj.__iter__()

    def keys(self):
        if not self.multiplatform:
            raise AttributeError(self.attribute_error_msg.format("keys"))
        return self.child_obj.keys()

    def values(self):
        if not self.multiplatform:
            raise AttributeError(self.attribute_error_msg.format("values"))
        return self.child_obj.values()

    def items(self):
        if not self.multiplatform:
            raise AttributeError(self.attribute_error_msg.format("items"))
        return self.child_obj.items()

    def item_initalization(self):
        if not self.group_item and not self.is_group:
            self.is_group = True

        self.multiplatform = self.schema_data.get("multiplatform", False)
        self.multipath = self.schema_data.get("multipath", False)
        self.with_arguments = self.schema_data.get("with_arguments", False)

        # Create child object
        if not self.multiplatform and not self.multipath:
            valid_value_types = (str, )
            item_schema = {
                "type": "path-input",
                "key": self.key,
                "with_arguments": self.with_arguments
            }

        elif not self.multiplatform:
            valid_value_types = (list, )
            item_schema = {
                "type": "list",
                "key": self.key,
                "object_type": {
                    "type": "path-input",
                    "with_arguments": self.with_arguments
                }
            }

        else:
            valid_value_types = (dict, )
            item_schema = {
                "type": "dict",
                "key": self.key,
                "show_borders": False,
                "children": []
            }
            for platform_key in self.platforms:
                platform_label = self.platform_labels_mapping[platform_key]
                child_item = {
                    "key": platform_key,
                    "label": platform_label
                }
                if self.multipath:
                    child_item["type"] = "list"
                    child_item["object_type"] = {
                        "type": "path-input",
                        "with_arguments": self.with_arguments
                    }
                else:
                    child_item["type"] = "path-input"
                    child_item["with_arguments"] = self.with_arguments

                item_schema["children"].append(child_item)

        self.valid_value_types = valid_value_types
        self.child_obj = self.create_schema_object(item_schema, self)

    def get_child_path(self, _child_obj):
        return self.path

    def set_value(self, value):
        self.child_obj.set_value(value)

    def settings_value(self):
        if self.override_state is OverrideState.NOT_DEFINED:
            return NOT_SET

        if self.is_group:
            if self.override_state is OverrideState.STUDIO:
                if not self.has_studio_override:
                    return NOT_SET
            elif self.override_state is OverrideState.PROJECT:
                if not self._has_project_override:
                    return NOT_SET

        return self.child_obj.settings_value()

    def on_value_change(self):
        raise NotImplementedError(self.__class__.__name__)

    def on_change(self):
        for callback in self.on_change_callbacks:
            callback()
        self.parent.on_child_change(self)

    def on_child_change(self, _child_obj):
        self.on_change()

    @property
    def child_has_studio_override(self):
        return self.child_obj.child_has_studio_override

    @property
    def child_is_modified(self):
        return self.child_obj.child_is_modified

    @property
    def child_has_project_override(self):
        return self.child_obj.child_has_project_override

    @property
    def value(self):
        return self.child_obj.value

    @property
    def has_unsaved_changes(self):
        return self.child_obj.has_unsaved_changes

    def set_override_state(self, state):
        self.child_obj.set_override_state(state)

    def update_default_value(self, value):
        self.child_obj.update_default_value(value)

    def update_project_values(self, value):
        self.child_obj.update_project_values(value)

    def update_studio_values(self, value):
        self.child_obj.update_studio_values(value)

    def discard_changes(self):
        self.child_obj.discard_changes()

    def remove_overrides(self):
        self.child_obj.remove_overrides()

    def reset_to_pype_default(self):
        self.child_obj.reset_to_pype_default()

    def set_as_overriden(self):
        self.child_obj.set_as_overriden()

    def set_studio_default(self):
        self.child_obj.set_studio_default()


class ListStrictEntity(ItemEntity):
    schema_types = ["list-strict"]

    gui_type = True

    child_has_studio_override = False
    child_has_project_override = False
    has_unsaved_changes = False
    child_is_modified = False

    # Abstract methods
    set_value = None
    on_change = None
    on_child_change = None
    on_value_change = None
    settings_value = None

    def item_initalization(self):
        self.valid_value_types = (list, )
        self.require_key = True

        self._current_value = NOT_SET
        # Child items
        self.object_types = self.schema_data["object_types"]

        self.children = []
        for children_schema in self.object_types:
            child_obj = self.create_schema_object(children_schema, self, True)
            self.children.append(child_obj)

        # GUI attribute
        self.is_horizontal = self.schema_data.get("horizontal", True)
        if not self.group_item and not self.is_group:
            self.is_group = True

    def get_child_path(self, child_obj):
        result_idx = None
        for idx, _child_obj in enumerate(self.children):
            if _child_obj is child_obj:
                result_idx = idx
                break

        if result_idx is None:
            raise ValueError("Didn't found child {}".format(child_obj))

        return "/".join([self.path, str(result_idx)])

    @property
    def value(self):
        return self._current_value

    def set_override_state(self, state):
        # TODO use right value as current_value is held here
        self.override_state = state
        if (
            not self.has_default_value
            and state in (OverrideState.STUDIO, OverrideState.PROJECT)
        ):
            raise DefaultsNotDefined(self)

        for child_obj in self.children:
            child_obj.set_override_state(state)

    def update_default_value(self, value):
        # TODO add value validation (length)
        self.has_default_value = value is not NOT_SET
        if value is NOT_SET:
            for child_obj in self.children:
                child_obj.update_default_value(value)

        else:
            for idx, item_value in enumerate(value):
                self.children[idx].update_default_value(item_value)

    def update_studio_values(self, value):
        if value is NOT_SET:
            for child_obj in self.children:
                child_obj.update_studio_values(value)

        else:
            for idx, item_value in enumerate(value):
                self.children[idx].update_studio_values(item_value)

    def update_project_values(self, value):
        if value is NOT_SET:
            for child_obj in self.children:
                child_obj.update_project_values(value)

        else:
            for idx, item_value in enumerate(value):
                self.children[idx].update_project_values(item_value)

    def discard_changes(self):
        pass

    def remove_overrides(self):
        pass

    def reset_to_pype_default(self):
        pass

    def set_as_overriden(self):
        pass

    def set_studio_default(self):
        pass
