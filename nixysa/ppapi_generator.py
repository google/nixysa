#!/usr/bin/python2.4
#
# Copyright 2011 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PPAPI glue generator.

This module implements the generator for PPAPI glue code.

For each class, the generator will create two pp::deprecated::ScriptableObject
classes:
  - one for the class instances, exposing all the member functions and
    properties, that wraps C++ instances. This one is created by the binding
    model module - this is called the 'instance object'
  - one for all the static members, like static functions and properties, but
    also inner types. Only one instance of this one will be created. This one
    is common to all the binding models, and is defined in static_object.h
    (glue::globals::StaticObjectWrapper) - this is called the 'static object'

For namespaces, one of the second type is created as well (containing global
functions and properties, and inner namespaces/classes).

That way if the IDL contains something like:

  namespace A {
    class B {
      static void C();
    };
  }

then one can access C in JavaScript through plugin.A.B.C();

The tricky part in this is that for namespaces, the definition of all the
members spans across multiple namespace definitions, possibly across multiple
files, but only one StaticObjectWrapper should exist, gathering all the members
from all the namespace definitions - that means the glue has to be generated for
all the definitions at once, generating the glue for each file separately will
not work. By convention, the PPAPI glue for a namespace will be defined in the
first file encountered that has a part of the namespace definition.

Because of that, the code generation happens in 2 passes. The first one
generates the code for all the definitions except the namespaces, and gather
all the data for the namespace generation. Then the second pass generates the
code for the namespaces.
"""

import string
import cpp_utils
import globals_binding
import idl_parser
import naming
import npapi_utils
import pod_binding
import syntax_tree


# default includes to add to the generated glue files

_cpp_includes = [('plugin_main.h', False),
                 ('ppapi/cpp/private/var_private.h', False)]

_header_includes = [('common.h', False),
                    ('static_object.h', False)]

# Header emitted for each static object
_class_glue_header_static = """
class StaticObject : public glue::globals::StaticObject {
 public:
  StaticObject();
  virtual void RegisterObjectBases(
      glue::globals::StaticObject* root_object);
  virtual void RegisterObjectWrappers(pp::InstancePrivate* instance);
  static glue::globals::StaticObject* GetStaticObject(
      glue::globals::StaticObject* root_object);
  virtual bool HasMethodInner(const std::string method);
  virtual bool HasPropertyInner(const std::string property);
  virtual bool GetPropertyInner(pp::InstancePrivate* instance,
                                const std::string property,
                                pp::Var* exception,
                                pp::Var* result);
  virtual void GetAllPropertyNames(std::vector<pp::Var>* names,
                                   pp::Var* exception);
  virtual bool SetPropertyInner(const std::string name,
                                const pp::Var& value,
                                pp::Var* exception);
  virtual bool CallInner(pp::InstancePrivate* instance,
                         const std::string method,
                         const std::vector<pp::Var>& args,
                         pp::Var* exception,
                         pp::Var* result);
  virtual bool ConstructInner(pp::InstancePrivate* instance,
                              const std::vector<pp::Var>& args,
                              pp::Var* exception,
                              pp::Var* result);
};
"""

# Header emitted for each instance object
_class_glue_header_member_base = """
class ObjectWrapper : public ${BaseClassNamespace}::ObjectWrapper {
"""

_class_glue_header_member_no_base = """
class ObjectWrapper : public ${BindingGlueBaseClass} {
"""

_class_glue_header_member_common = """
public:
  explicit ObjectWrapper(pp::InstancePrivate* instance);
  ~ObjectWrapper();
  virtual bool HasMethodInner(const std::string method);
  virtual bool HasPropertyInner(const std::string name);
  virtual bool GetPropertyInner(${ClassParamType} object,
                                const std::string name,
                                pp::Var* exception,
                                pp::Var* result);
  virtual pp::Var GetProperty(const pp::Var& name,
                              pp::Var* exception);
  virtual void GetAllPropertyNames(std::vector<pp::Var>* properties,
                                   pp::Var* exception);
  virtual bool SetPropertyInner(${ClassMutableParamType} object,
                                const std::string name,
                                const pp::Var& value,
                                pp::Var* exception);
  virtual void SetProperty(const pp::Var& name,
                           const pp::Var& value,
                           pp::Var* exception);
  virtual pp::Var Call(const pp::Var& name,
                       const std::vector<pp::Var>& args,
                       pp::Var* exception);
  virtual bool CallInner(${ClassMutableParamType} object,
                         std::string name,
                         const std::vector<pp::Var>& args,
                         pp::Var* exception,
                         pp::Var* result);
  static void RegisterWrapper(pp::InstancePrivate* instance);
${BindingGlueHeader}
};
"""

_class_glue_header_base_template = string.Template(
    _class_glue_header_static +
    _class_glue_header_member_base +
    _class_glue_header_member_common)

_class_glue_header_no_base_template = string.Template(
    _class_glue_header_static +
    _class_glue_header_member_no_base +
    _class_glue_header_member_common)

#_class_glue_header_template = string.Template(_class_glue_header_static +
#                                              _class_glue_header_member)

_class_glue_cpp_common_head_static = """
StaticObject::StaticObject() :
    glue::globals::StaticObject() {
  ${#CreateNamespaces}
}

void StaticObject::RegisterObjectBases(
    glue::globals::StaticObject *root_object) {
  ${#RegisterBases}
}

void StaticObject::RegisterObjectWrappers(pp::InstancePrivate* instance) {
  ${#InitNamespaceGlues}

  ${#RegisterObjectWrappers}
}

bool StaticObject::HasMethodInner(const std::string method) {
  ${#StaticHasMethodCode}
  return glue::globals::StaticObject::HasMethodInner(method);
}

bool StaticObject::HasPropertyInner(const std::string property) {
  ${#StaticHasPropertyCode}
  return glue::globals::StaticObject::HasPropertyInner(property);
}

bool StaticObject::GetPropertyInner(pp::InstancePrivate* instance,
                                    const std::string property,
                                    pp::Var* exception,
                                    pp::Var* result) {
  ${#StaticGetPropertyCode}
  return glue::globals::StaticObject::GetPropertyInner(instance,
                                                       property,
                                                       exception,
                                                       result);
}

void StaticObject::GetAllPropertyNames(std::vector<pp::Var>*names,
                                       pp::Var* exception) {
  ${#StaticGetAllPropertyNamesCode}
}

bool StaticObject::SetPropertyInner(const std::string name,
                                    const pp::Var& value,
                                    pp::Var* exception) {
  ${#StaticSetPropertyCode}
  return glue::globals::StaticObject::SetPropertyInner(name, value, exception);
}

bool StaticObject::CallInner(pp::InstancePrivate* instance,
                             const std::string name,
                             const std::vector<pp::Var>& args,
                             pp::Var* exception,
                             pp::Var* result) {
  uint32_t argCount = args.size();
  ${#StaticInvokeCode}
  return glue::globals::StaticObject::CallInner(instance, name, args,
                                                exception, result);
}

bool StaticObject::ConstructInner(pp::InstancePrivate* instance,
                                  const std::vector<pp::Var>& args,
                                  pp::Var* exception,
                                  pp::Var* result) {
  uint32_t argCount = args.size();
  bool success = true;
  GLUE_SCOPED_PROFILE(instance, "${Class}::Construct", prof);
  ${#StaticInvokeDefaultCode}
  GLUE_SCOPED_PROFILE_STOP(prof);
  if (!success && exception->is_string())
    glue::globals::SetLastError(instance, exception->AsString().c_str());
  if (!exception->is_string())
    *exception = pp::Var("missing constructor");
  return false;
}

${#GetStaticObjects}
"""

# Area for instance cpp code common to all bindings / base/no-base variations
_class_glue_cpp_common_head_member = """
pp::Var ObjectWrapper::GetProperty(const pp::Var& name, pp::Var* exception) {
  bool success = true;
  GLUE_SCOPED_PROFILE(plugin_instance(), std::string("${Class}::GetProperty(") +
      (name.is_string() ? name.AsString() : "") + ")", prof);
  pp::Var result = pp::Var();
  ${DispatchFunctionHeader}
  if (!success) {
    *exception = "unable to find object";
    return pp::Var();
  }
  if (!name.is_string()) {
    *exception = pp::Var("property name is not a string");
    return result;
  }
  bool ret = GetPropertyInner(${ObjectNonMutable}, name.AsString(),
                              exception, &result);
  GLUE_SCOPED_PROFILE_STOP(prof);
  if (!ret && exception->is_string())
    glue::globals::SetLastError(plugin_instance(),
                                exception->AsString().c_str());
  return result;
}

void ObjectWrapper::SetProperty(const pp::Var& name, const pp::Var& val,
                                pp::Var* exception) {
  bool success = true;
  GLUE_SCOPED_PROFILE(plugin_instance(), std::string("${Class}::SetProperty(") +
      (name.is_string() ? name.AsString() : "") + ")", prof);
  ${DispatchFunctionHeader}
  if (!success) {
    *exception = pp::Var("unable to find object");
    return;
  }
  if (!name.is_string()) {
    *exception = pp::Var("property name is not a string");
    return;
  }
  bool ret = SetPropertyInner(${Object}, name.AsString(), val, exception);
  GLUE_SCOPED_PROFILE_STOP(prof);
  if (!ret && exception->is_string()) {
    glue::globals::SetLastError(plugin_instance(),
                                exception->AsString().c_str());
  }
}

pp::Var ObjectWrapper::Call(const pp::Var& name,
                            const std::vector<pp::Var>& args,
                            pp::Var* exception) {
  bool success = true;
  GLUE_SCOPED_PROFILE(plugin_instance(), std::string("${Class}::Call(") +
      (name.is_string() ? name.AsString() : "") + ")", prof);
  pp::Var result = pp::Var();
  ${DispatchFunctionHeader}
  if (!success) {
    *exception = "unable to find object";
    return result;
  }
  if (!name.is_string()) {
    *exception = pp::Var("method name is not a string");
    return result;
  }
  bool ret = CallInner(${Object}, name.AsString(),
     args, exception, &result);
  GLUE_SCOPED_PROFILE_STOP(prof);
  if (!ret && exception->is_string())
    glue::globals::SetLastError(plugin_instance(),
                                exception->AsString().c_str());
  return result;
}
"""

# Emitted for an instance object that has a base (super) class
_class_glue_cpp_base_member = """
ObjectWrapper::~ObjectWrapper() {}

bool ObjectWrapper::HasMethodInner(const std::string method) {
  ${#HasMethodCode}
  return ${BaseClassNamespace}::ObjectWrapper::HasMethodInner(method);
}

bool ObjectWrapper::HasPropertyInner(const std::string name ) {
  ${#HasPropertyCode}
  return ${BaseClassNamespace}::ObjectWrapper::HasPropertyInner(name);
}

bool ObjectWrapper::GetPropertyInner(${ClassParamType} object,
                                     const std::string name,
                                     pp::Var* exception,
                                     pp::Var* result) {
  pp::InstancePrivate* instance = plugin_instance();
  ${#GetPropertyCode}
  return ${BaseClassNamespace}::ObjectWrapper::GetPropertyInner(object,
                                                                name,
                                                                exception,
                                                                result);
}

void ObjectWrapper::GetAllPropertyNames(std::vector<pp::Var>*names,
                                        pp::Var* exception) {
  ${#GetAllPropertyNamesCode}
  ${BaseClassNamespace}::ObjectWrapper::GetAllPropertyNames(names, exception);
}

bool ObjectWrapper::SetPropertyInner(${ClassMutableParamType} object,
                                     const std::string name,
                                     const pp::Var& value,
                                     pp::Var* exception) {
  pp::InstancePrivate* instance = plugin_instance();
  ${#SetPropertyCode}
  return ${BaseClassNamespace}::ObjectWrapper::SetPropertyInner(object,
                                                                name,
                                                                value,
                                                                exception);
}

bool ObjectWrapper::CallInner(${ClassMutableParamType} object,
                              std::string name,
                              const std::vector<pp::Var>& args,
                              pp::Var* exception,
                              pp::Var* result) {
  uint32_t argCount = args.size();
  pp::InstancePrivate* instance = plugin_instance();
  ${#InvokeCode}
  return ${BaseClassNamespace}::ObjectWrapper::CallInner(object,
                                                         name,
                                                         args,
                                                         exception,
                                                         result);
}

${BindingGlueCpp}
"""

_class_glue_cpp_no_base_member = """
ObjectWrapper::~ObjectWrapper() {}

bool ObjectWrapper::HasMethodInner(const std::string method) {
  ${#HasMethodCode}
  return false;
}

bool ObjectWrapper::HasPropertyInner(const std::string name ) {
  ${#HasPropertyCode}
  return false;
}

bool ObjectWrapper::GetPropertyInner(${ClassParamType} object,
                                     const std::string name,
                                     pp::Var* exception,
                                     pp::Var* result) {
  pp::InstancePrivate* instance = plugin_instance();
  ${#GetPropertyCode}
  if (exception->is_null())
    *exception = pp::Var("property does not exist");
  return false;
}

void ObjectWrapper::GetAllPropertyNames(std::vector<pp::Var>*names,
                                        pp::Var* exception) {
  ${#GetAllPropertyNamesCode}
  pp::deprecated::ScriptableObject::GetAllPropertyNames(names, exception);
}

bool ObjectWrapper::SetPropertyInner(${ClassMutableParamType} object,
                                     const std::string name,
                                     const pp::Var& value,
                                     pp::Var* exception) {
  pp::InstancePrivate* instance = plugin_instance();
  ${#SetPropertyCode}
  if (exception->is_null())
    *exception = "Property can not be set";
  return false;
}

bool ObjectWrapper::CallInner(${ClassMutableParamType} object,
                              std::string name,
                              const std::vector<pp::Var>& args,
                              pp::Var* exception,
                              pp::Var* result) {
  uint32_t argCount = args.size();
  pp::InstancePrivate* instance = plugin_instance();
  ${#InvokeCode}
  if (exception->is_null())
    *exception = "method does not exist";
  return false;
}

${BindingGlueCpp}
"""

_class_glue_cpp_base_template = string.Template(''.join([
    _class_glue_cpp_common_head_static,
    _class_glue_cpp_common_head_member,
    _class_glue_cpp_base_member]))

_class_glue_cpp_no_base_template = string.Template(''.join([
    _class_glue_cpp_common_head_static,
    _class_glue_cpp_common_head_member,
    _class_glue_cpp_no_base_member]))

_namespace_glue_header = _class_glue_header_static

_namespace_glue_cpp_template = string.Template(''.join([
    _class_glue_cpp_common_head_static]))

_callback_glue_cpp_template = string.Template("""
${RunCallback} {
  ${StartException}
  bool success = true;
  pp::Var args[${ArgCount}];
  pp::VarPrivate priv(object);
  pp::Var exception_local = pp::Var();
  pp::Var* exception = &exception_local;
  ${ParamsToVariantsPre}
  if (success) {
    ${ParamsToVariantsPost}
    GLUE_PROFILE_START(instance, "invokeDefault");
    pp::Var result = priv.Call(pp::Var(), ${ArgCount}, args, exception);
    GLUE_PROFILE_STOP(instance, "invokeDefault");
  }
  ${ReturnEval}
  return ${ReturnValue};
  ${EndException}
}
""")

_callback_no_param_glue_cpp_template = string.Template("""
${RunCallback} {
  ${StartException}
  pp::Var exception = pp::Var();
  bool success = true;
  pp::VarPrivate priv(object);
  GLUE_PROFILE_START(instance, "invokeDefault");
  pp::Var result = priv.Call(pp::Var(), &exception);
  GLUE_PROFILE_STOP(instance, "invokeDefault");
  ${ReturnEval}
  return ${ReturnValue};
  ${EndException}
}
""")


_initialize_glue_template = string.Template(
    '${Namespace}::ObjectWrapper::RegisterWrapper(instance);')

_create_namespace_template = string.Template("""
glue::globals::StaticObject* namespace_${Name} =
  new ${Namespace}::StaticObject();
AddNamespaceObject("${Name}", namespace_${Name});
""")

_register_base_template = string.Template("""
{
  glue::globals::StaticObject* obj =
    GetNamespaceObject("${Name}");
  obj->SetBaseClass(
      ${BaseClassNamespace}::StaticObject::GetStaticObject(root_object));
  obj->RegisterObjectBases(root_object);
}
""")

_register_no_base_template = string.Template(
"""GetNamespaceObject("${Name}")->RegisterObjectBases(root_object);"""
)

_register_objectwrapper_template = string.Template(
"""GetNamespaceObject("${Name}")->RegisterObjectWrappers(instance);"""
)

_get_ns_object_template = string.Template("""
namespace ${Namespace} {
  glue::globals::StaticObject* StaticObject::GetStaticObject(
      glue::globals::StaticObject* root_object) {
  glue::globals::StaticObject* parent =
      ${ParentNamespace}::StaticObject::GetStaticObject(root_object);
  return (parent->GetNamespaceObject("${Name}"));
}
}  // namespace ${Namespace}
""")

# code pieces templates

_method_call_template = string.Template("""
  if (name == ${method_name} && argCount == ${argCount}) do {
    bool success = true;
    ${code}
  } while(false);""")

_method_default_invoke_template = string.Template("""
  if (argCount == ${argCount}) do {
    bool success = true;
    ${code}
  } while(false);""")

_property_template = string.Template("""
  if (name == ${Name}) do {
    bool success = true;
    ${code}
  } while(false);""")

_enum_template = string.Template("""
if (property==\"${Enum}\") {
  *result = pp::Var(${Namespace}::${Enum});
  return true;
}""")

_failure_test_string = '    if (!success) break;'

_exception_context_start_template = string.Template(
    """#define ${exception_macro_name} "${type} '${name}'" """)

_exception_context_end_template = string.Template(
    """#undef ${exception_macro_name}""")

_exception_macro_name = 'PPAPI_GLUE_EXCEPTION_CONTEXT'

def GenExceptionContext(exception_macro_name, type, name):
  """Create code to define the context for exception error messages.

  Args:
    exception_macro_name: the name to use for the macro
    type: the type of access that name represents (field, parameter, etc.)
    name: the name of the variable

  Returns:
    a tuple of 2 strings; the first #defines the text to stick in the
    exception, and the second #undefs the string to clean up the namespace.
  """
  start = _exception_context_start_template.substitute(type=type,
                                                       name=name,
                                                       exception_macro_name=
                                                           exception_macro_name)
  end = _exception_context_end_template.substitute(exception_macro_name=
                                                       exception_macro_name)
  return (start, end)


def GetGlueHeader(idl_file):
  """Gets the name of the glue header file.

  Args:
    idl_file: an idl_parser.File, the source IDL file.

  Returns:
    the name of the header file.
  """
  if 'npapi_header' in idl_file.__dict__:
    return idl_file.npapi_header
  else:
    return idl_file.basename + '_glue.h'


def GetGlueCpp(idl_file):
  """Gets the name of the glue implementation file.

  Args:
    idl_file: an idl_parser.File, the source IDL file.

  Returns:
    the name of the implementation file.
  """
  if 'npapi_cpp' in idl_file.__dict__:
    return idl_file.npapi_cpp
  else:
    return idl_file.basename + '_glue.cc'


class MethodWithoutReturnType(Exception):
  """Raised when finding a function without return type."""

  def __init__(self, obj):
    Exception.__init__(self)
    self.object = obj


def GenNamespaceCode(context):
  """Generates the code for namespace glue.

  This function generates the necessary code to initialize the
  globals::StaticObjectWrapper instance with the inner namespace objects.

  Args:
    context: the PpapiGenerator.CodeGenContext for generating the glue.

  Returns:
    a dict is generated by npapi_utils.MakeIdTableDict, and contains the
    substitution strings for the namespace ids.
  """
  namespace_ids = []
  if context.namespace_list:
    for ns_obj in context.namespace_list:
      id_enum = 'SCOPE_%s' % naming.Normalize(ns_obj.name, naming.Upper)
      namespace_ids.append((id_enum, '"%s"' % ns_obj.name))
      full_namespace = npapi_utils.GetGlueFullNamespace(ns_obj)
      context.namespace_create_section.EmitCode(
          _create_namespace_template.substitute(Namespace=full_namespace,
                                                Name=ns_obj.name))
      if ns_obj.defn_type == 'Class' and ns_obj.base_type:
        base_class_namespace = npapi_utils.GetGlueFullNamespace(
            ns_obj.base_type.GetFinalType())
        context.namespace_register_base_section.EmitCode(
            _register_base_template.substitute(
                Name=ns_obj.name,
                BaseClassNamespace=base_class_namespace,
                Namespace=full_namespace))
      else:
        context.namespace_register_base_section.EmitCode(
            _register_no_base_template.substitute(Name=ns_obj.name,
                                                  Namespace=full_namespace))
        context.namespace_register_objectwrapper_section.EmitCode(
            _register_objectwrapper_template.substitute(Name=ns_obj.name))

      if ns_obj.defn_type == 'Class':
        context.namespace_init_section.EmitCode(
            _initialize_glue_template.substitute(Namespace=full_namespace))
 

      context.namespace_get_static_object_section.EmitCode(
          _get_ns_object_template.substitute(
              Namespace=npapi_utils.GetGlueNamespace(ns_obj.GetFinalType()),
              ParentNamespace=npapi_utils.GetGlueFullNamespace(
                  ns_obj.parent.GetFinalType()),
              Name=ns_obj.name))
  return npapi_utils.MakeIdTableDict(namespace_ids, 'namespace')


def MakePodType(name):
  """Creates a pod type with reasonable attributes.

  This function is used to be able to generate parameters that are not directly
  referenced in the IDL

  Args:
    name: the name of the pod type.

  Returns:
    a Definition for the type.
  """
  source_file = idl_parser.File('<internal>')
  source_file.header = None
  source_file.npapi_cpp = None
  source_file.npapi_header = None
  source = idl_parser.SourceLocation(source_file, 0)
  attributes = {'binding_model': 'pod'}
  type_defn = syntax_tree.Typename(source, attributes, name)
  type_defn.binding_model = pod_binding
  type_defn.podtype = 'variant'
  return type_defn


class PpapiGenerator(object):
  """Main generator class."""

  def __init__(self, output_dir):
    """Inits a PpapiGenerator instance.

    Args:
      output_dir: the output directory for generated files.
    """
    self._output_dir = output_dir
    self._namespace_map = {}
    self._finalize_functions = []
    # TODO: instead of passing a raw void *, it would be better to define a
    # PluginInstance class. Needs a fair amount of refactoring in the C++ code.
    self._plugin_data_type = MakePodType('void *')

  class CodeGenContext(object):
    """Code generation context.

    This class gathers all the data that needs to be passed around in code
    generation functions.

    Note: the section fields of this class are generated programatically.

    Attributes:
      type: the container type (can be a Class or a Namespace).
      binding_model: the binding model for the containing type.
      is_namespace: whether or not the container is a namespace.
      scope: current code generation scope, to generate properly qualified type
        references.
      header_section: the current code section in the header file.
      cpp_section: the current code section in the implementation file.
      static_prop_ids: the list of (enum_name, JS name) for properties in the
        static object for the container type.
      static_method_ids: the list of (enum_name, JS name) for methods in the
        static object for the container type.
      namespace_list: the list of inner namespace and classes of the container
        type (to generate the static object)
      prop_ids: the list of (enum_name, JS name) for properties in the
        instance object for the container type.
      method_ids: the list of (enum_name, JS name) for methods in the
        instance object for the container type.
      namespace_init_section: a section where the initialization code for the
        namespaces in the static object will go.
      namespace_create_section: a section where the globals::StaticObjectWrapper
        creation code will go.
      namespace_register_base_section: a section where the class bases get
        registered into their corresponding globals::StaticObjectWrapper.
      namespace_get_static_object_section: a section where the
        GetStaticObject functions get defined.
      static_invoke_section: a section where the Invoke implementation for the
        static object will go (for static functions).
      static_invoke_default_section: a section where the InvokeDefault
        implementation for the static object will go (for constructors).
      static_get_prop_section: a section where the GetProperty implementation
        for the static object will go (for static members, enum values, and
        inner namespaces).
      static_set_prop_section: a section where the SetProperty implementation
        for the static object will go (for static members).
      invoke_section: a section where the Invoke implementation for the
        instance object will go (for non-static methods).
      get_prop_section: a section where the GetProperty implementation for the
        instance object will go (for non-static members).
      set_prop_section: a section where the SetProperty implementation for the
        instance object will go (for non-static members).
    """

    _sections = [('namespace_init_section', 'InitNamespaceGlues'),
                 ('namespace_create_section', 'CreateNamespaces'),
                 ('namespace_register_base_section', 'RegisterBases'),
                 ('namespace_register_objectwrapper_section',
                     'RegisterObjectWrappers'),
                 ('namespace_get_static_object_section', 'GetStaticObjects'),
                 ('static_invoke_section', 'StaticInvokeCode'),
                 ('static_invoke_default_section', 'StaticInvokeDefaultCode'),
                 ('static_has_method_section', 'StaticHasMethodCode'),
                 ('static_get_prop_section', 'StaticGetPropertyCode'),
                 ('static_has_prop_section', 'StaticHasPropertyCode'),
                 ('static_get_all_property_names_section',
                     'StaticGetAllPropertyNamesCode'),
                 ('static_set_prop_section', 'StaticSetPropertyCode')]

    _class_sections = [('invoke_section', 'InvokeCode'),
                       ('get_prop_section', 'GetPropertyCode'),
                       ('get_all_property_names_section',
                           'GetAllPropertyNamesCode'),
                       ('set_prop_section', 'SetPropertyCode'),
                       ('has_method_section', 'HasMethodCode'),
                       ('has_property_section', 'HasPropertyCode')]

    def __init__(self, type_defn, scope, header_section, cpp_section,
                 share_context):
      """Inits a CodeGenContext.

      Args:
        type_defn: the container type.
        scope: current code generation scope, to generate properly qualified
          type references.
        header_section: the current code section in the header file.
        cpp_section: the current code section in the implementation file.
        share_context: share the definition sections and the id lists with that
          context (can be None) - used when encountering namespaces defined
          previously.
      """
      self.type_defn = type_defn
      self.binding_model = type_defn.binding_model or globals_binding
      self.is_namespace = type_defn.defn_type == 'Namespace'
      self.scope = scope
      self.header_section = header_section
      self.cpp_section = cpp_section
      if self.is_namespace:
        all_sections = self._sections
      else:
        all_sections = self._sections + self._class_sections
      if share_context:
        self.static_prop_ids = share_context.static_prop_ids
        self.static_method_ids = share_context.static_method_ids
        self.namespace_list = share_context.namespace_list
        if not share_context.is_namespace:
          self.prop_ids = share_context.prop_ids
          self.method_ids = share_context.method_ids
        # programmatically copy fields
        for field_name, section_name in all_sections:
          setattr(self, field_name, getattr(share_context, field_name))
      else:
        self.static_prop_ids = []
        self.static_method_ids = []
        self.namespace_list = []
        if not self.is_namespace:
          self.prop_ids = []
          self.method_ids = []
        # programmatically create fields
        for field_name, section_name in all_sections:
          setattr(self, field_name,
                  cpp_section.CreateUnlinkedSection(section_name))
          getattr(self, field_name).needed_glue = cpp_section.needed_glue

  def GetParamInputStrings(self, scope, param_list):
    """Gets the code to retrieve parameters from an array of pp::Var.

    Args:
      scope: the code generation scope.
      param_list: a list of Function.Param.

    Returns:
      a 3-uple. The first element is a list of strings that contains the code
      to retrieve the parameter values. The second element is a list of
      expressions to access each of the parameters. The third element is the set
      of all the types whose glue header is needed.
    """
    strings = []
    param_names = []
    needed_glue = set()
    for i in range(len(param_list)):
      param = param_list[i]
      needed_glue.add(param.type_defn)
      param_binding = param.type_defn.binding_model
      start_exception, end_exception = GenExceptionContext(
          _exception_macro_name, "parameter",
          naming.Normalize(param.name, naming.Java))
      code, param_access = param_binding.PpapiFromPPVar(
          scope, param.type_defn, 'args[%d]' % i, 'param_%s' % param.name,
          'success', _exception_macro_name, 'instance')
      strings.append(start_exception)
      strings.append(code)
      strings.append(_failure_test_string)
      strings.append(end_exception)
      param_names.append(param_access)
    return strings, param_names, needed_glue

  def GetReturnStrings(self, scope, type_defn, expression, result):
    """Gets the code to set a return value into a pp::Var.

    Args:
      scope: the code generation scope.
      type_defn: the type of the return value.
      expression: the expression that evaluates to the return value.
      result: the expression that evaluates to a pointer to the pp::Var.

    Returns:
      a 3-uple. The first element is the code to generate the
      pp::Var-compatible value (that can fail). The second element is the
      code to set the pp::Var. The third element is the set of all the types
      whose glue header is needed.
    """
    binding_model = type_defn.binding_model
    pre, post = binding_model.PpapiExprToPPVar(scope, type_defn, 'retval',
                                               expression, result,
                                               'success', 'instance')
    return pre, post, set([type_defn])

  def GetVoidReturnStrings(self, type_defn, result):
    """Gets the code to return a void value for a write-only member.

    Args:
      type_defn: the type of the return value.
      result: the expression that evaluates to a pointer to the pp::Var.

    Returns:
      a 3-uple. The first element is empty, and is needed only to mimic the
      return of GetReturnStrings. The second element is the code to set the
      pp::Var. The third element is the set of all the types whose glue
      header is needed.
    """
    post = "*%s = pp::Var();\n" % result
    return "", post, set([type_defn])

  def GenerateCppFunction(self, section, scope, function):
    """Generates a function header.

    Args:
      section: the code section to generate the function header into.
      scope: the code generation scope.
      function: the Function to generate.
    """
    prototype, unused_val = cpp_utils.GetFunctionPrototype(scope, function, '')
    section.EmitCode(prototype + ';')

  def GetUserGlueMethodFunc(self, scope, type_defn, method):
    """Creates a definition for the user glue function for a non-static method.

    Args:
      scope: the code generation scope.
      type_defn: the type of the method container.
      method: the method for which to create the user glue function.

    Returns:
      a syntax_tree.Function for the user glue function.
    """
    glue_function = syntax_tree.Function(method.source, [],
                                         'userglue_method_%s' % method.name,
                                         None, [])
    glue_function.type_defn = method.type_defn
    glue_function.parent = scope
    this_param = syntax_tree.Function.Param(type_defn.name, '_this')
    this_param.type_defn = type_defn
    this_param.mutable = True
    glue_function.params = [this_param] + method.params
    return glue_function

  def GetUserGlueStaticMethodFunc(self, scope, method):
    """Creates a definition for the user glue function for a static function.

    Args:
      scope: the code generation scope.
      method: the method for which to create the user glue function.

    Returns:
      a syntax_tree.Function for the user glue function.
    """
    glue_function = syntax_tree.Function(method.source, [],
                                         'userglue_static_%s' % method.name,
                                         None, [])
    glue_function.type_defn = method.type_defn
    glue_function.params = method.params[:]
    glue_function.parent = scope
    return glue_function

  def GetUserGlueConstructorFunc(self, scope, type_defn, method):
    """Creates a definition for the user glue function for a constructor.

    Args:
      scope: the code generation scope.
      type_defn: the type of the method container.
      method: the constructor for which to create the user glue function.

    Returns:
      a syntax_tree.Function for the user glue function.
    """
    glue_function = syntax_tree.Function(method.source, [],
                                         'userglue_construct_%s' % method.name,
                                         None, [])
    glue_function.type_defn = type_defn
    glue_function.params = method.params[:]
    glue_function.parent = scope
    return glue_function

  def GetUserGlueSetterFunc(self, scope, type_defn, field):
    """Creates a definition for the user glue function for a setter method.

    For a field name 'myField' of type "FieldType" in an object of type
    'ObjectType', this creates a function like:
    void userglue_setter_myField(ObjectType _this, FieldType param_myField)

    Args:
      scope: the code generation scope.
      type_defn: the type of the method container.
      method: the method for which to create the user glue function.

    Returns:
      a syntax_tree.Function for the user glue function.
    """
    glue_function = syntax_tree.Function(field.source, [],
                                         'userglue_setter_%s' % field.name,
                                         None, [])
    glue_function.type_defn = scope.LookUpTypeRecursive('void')
    glue_function.parent = scope
    this_param = syntax_tree.Function.Param(type_defn.name, '_this')
    this_param.type_defn = type_defn
    this_param.mutable = True
    value_param = syntax_tree.Function.Param(type_defn.name, 'param_' +
                                             field.name)
    value_param.type_defn = field.type_defn
    glue_function.params = [this_param, value_param]
    return glue_function

  def GetUserGlueGetterFunc(self, scope, type_defn, field):
    """Creates a definition for the user glue function for a getter method.

    For a field name 'myField' of type "FieldType" in an object of type
    'ObjectType', this creates a function like:
    FieldType userglue_getter_myField(ObjectType _this)

    Args:
      scope: the code generation scope.
      type_defn: the type of the method container.
      method: the method for which to create the user glue function.

    Returns:
      a syntax_tree.Function for the user glue function.
    """
    glue_function = syntax_tree.Function(field.source, [],
                                         'userglue_getter_%s' % field.name,
                                         None, [])
    glue_function.type_defn = field.type_defn
    glue_function.parent = scope
    this_param = syntax_tree.Function.Param(type_defn.name, '_this')
    this_param.type_defn = type_defn
    this_param.mutable = True
    glue_function.params = [this_param]
    return glue_function

  def AddPluginDataParam(self, scope, func, param_exprs):
    """Adds the plugin data parameter to a function and parameter list.

    Args:
      scope: the scope for the parameter type.
      func: the function to which we add a parameter.
      param_exprs: the list of parameters exressions to which the plugin data
        is added
    """
    scope = scope  # silence gpylint
    plugin_data_param = syntax_tree.Function.Param(
        self._plugin_data_type.name, 'plugin_data')
    plugin_data_param.type_defn = self._plugin_data_type
    func.params.insert(0, plugin_data_param)
    param_exprs.insert(0, 'instance')

  def EmitMemberCall(self, context, func):
    """Emits the glue for a non-static member function call.

    Args:
      context: the code generation context.
      func: the method to call.
    """
    scope = context.scope
    type_defn = context.type_defn
    binding_model = context.binding_model
    
    section = context.invoke_section
    id_enum = 'METHOD_%s' % naming.Normalize(func.name, naming.Upper)
    quoted_name = '"%s"' % naming.Normalize(func.name, naming.Java)
    context.method_ids.append((id_enum, quoted_name))
    has_method_glue = "if (method==%s) return true;" % quoted_name
    context.has_method_section.EmitCode(has_method_glue)
    strings, param_exprs, needed_glue = self.GetParamInputStrings(scope,
                                                                  func.params)
    section.needed_glue.update(needed_glue)
    if 'userglue' in func.attributes:
      glue_func = self.GetUserGlueMethodFunc(scope, type_defn, func)
      param_exprs.insert(0, 'object')
      if 'plugin_data' in func.attributes:
        self.AddPluginDataParam(context.scope, glue_func, param_exprs)
      self.GenerateCppFunction(context.header_section, scope, glue_func)
      expression = globals_binding.CppCallStaticMethod(scope, scope, glue_func,
                                                       param_exprs)
    else:
      expression = binding_model.CppCallMethod(scope, type_defn, 'object',
                                               True, func, param_exprs)
    pre, post, needed_glue = self.GetReturnStrings(scope, func.type_defn,
                                                   expression, 'result')
    section.needed_glue.update(needed_glue)
    strings += [pre, _failure_test_string, post, 'return true;']
    self.EmitCallCode(section, quoted_name, len(func.params),
        '\n'.join(strings))


  def EmitStaticCall(self, context, func):
    """Emits the glue for a static function call.

    Args:
      context: the code generation context.
      func: the function to call.
    """
    scope = context.scope
    type_defn = context.type_defn
    binding_model = context.binding_model
    id_enum = 'STATIC_METHOD_%s' % naming.Normalize(func.name, naming.Upper)
    name = '"%s"' % naming.Normalize(func.name, naming.Java)
    context.static_method_ids.append((id_enum, name))
    section = context.static_has_method_section
    has_method_glue = "if (method==%s) return true;" % name
    section.EmitCode(has_method_glue)

    strings, param_exprs, needed_glue = self.GetParamInputStrings(scope,
                                                                  func.params)
    section = context.static_invoke_section
    section.needed_glue.update(needed_glue)
    if 'userglue' in func.attributes:
      glue_func = self.GetUserGlueStaticMethodFunc(scope, func)
      if 'plugin_data' in func.attributes:
        self.AddPluginDataParam(context.scope, glue_func, param_exprs)
      self.GenerateCppFunction(context.header_section, scope, glue_func)
      expression = globals_binding.CppCallStaticMethod(scope, scope, glue_func,
                                                       param_exprs)
    else:
      expression = binding_model.CppCallStaticMethod(scope, type_defn, func,
                                                     param_exprs)
    pre, post, needed_glue = self.GetReturnStrings(scope, func.type_defn,
                                                   expression, 'result')
    section.needed_glue.update(needed_glue)
    strings += [pre, _failure_test_string, post, 'return true;']
    self.EmitCallCode(section, name, len(func.params), '\n'.join(strings))

  def EmitConstructorCall(self, context, func):
    """Emits the glue for a constructor call.

    Args:
      context: the code generation context.
      func: the constructor to call.
    """
    scope = context.scope
    type_defn = context.type_defn
    binding_model = context.binding_model
    section = context.static_invoke_default_section
    strings, param_exprs, needed_glue = self.GetParamInputStrings(scope,
                                                                  func.params)
    section.needed_glue.update(needed_glue)
    if 'userglue' in func.attributes:
      glue_func = self.GetUserGlueConstructorFunc(scope, type_defn, func)
      if 'plugin_data' in func.attributes:
        self.AddPluginDataParam(context.scope, glue_func, param_exprs)
      self.GenerateCppFunction(context.header_section, scope, glue_func)
      expression = globals_binding.CppCallStaticMethod(scope, scope, glue_func,
                                                       param_exprs)
    else:
      expression = binding_model.CppCallConstructor(scope, type_defn, func,
                                                    param_exprs)
    pre, post, needed_glue = self.GetReturnStrings(scope, type_defn, expression,
                                                   'result')
    section.needed_glue.update(needed_glue)
    strings += [pre, _failure_test_string, post, 'return true;']
    self.EmitInvokeDefaultCode(section, len(func.params), '\n'.join(strings))

  def EmitMemberProp(self, context, field):
    """Emits the glue for a non-static member field access.

    Args:
      context: the code generation context.
      field: the field to access.
    """
    scope = context.scope
    type_defn = context.type_defn
    binding_model = context.binding_model
    id_enum = 'PROPERTY_%s' % naming.Normalize(field.name, naming.Upper)
    prop_name = '"%s"' % naming.Normalize(field.name, naming.Java)
    context.prop_ids.append((id_enum, prop_name))
    has_property_glue = "if (name==%s) return true;" % prop_name
    get_all_prop_names_glue_code = "names->push_back(%s);" % prop_name
    context.has_property_section.EmitCode(has_property_glue)
    context.get_all_property_names_section.EmitCode(
        get_all_prop_names_glue_code)
    if 'getter' in field.attributes:
      if 'userglue_getter' in field.attributes:
        glue_func = self.GetUserGlueGetterFunc(scope, type_defn, field)
        param_exprs = ['object']
        if 'plugin_data' in field.attributes:
          self.AddPluginDataParam(scope, glue_func, param_exprs)
        self.GenerateCppFunction(context.header_section, scope, glue_func)
        expression = globals_binding.CppCallStaticMethod(scope, scope,
                                                         glue_func, param_exprs)
      else:
        expression = binding_model.CppGetField(scope, type_defn, 'object',
                                               field)
      pre, post, needed_glue = self.GetReturnStrings(scope, field.type_defn,
                                                     expression, 'result')
    else:
      # Return a void value for write-only members.
      pre, post, needed_glue = self.GetVoidReturnStrings(field.type_defn,
                                                         'result')

    section = context.get_prop_section
    section.needed_glue.update(needed_glue)
    get_string = '\n'.join([pre, _failure_test_string, post, 'return true;'])
    self.EmitPropertyCode(section, prop_name, get_string)

    if 'setter' in field.attributes:
      # TODO: Add a specific error for trying to set a read-only prop.
      field_binding = field.type_defn.binding_model
      start_exception, end_exception = GenExceptionContext(
          _exception_macro_name, "field",
          naming.Normalize(field.name, naming.Java))
      code, param_expr = field_binding.PpapiFromPPVar(
          scope, field.type_defn, 'value', 'param_%s' % field.name,
          'success', _exception_macro_name, 'instance')
      section = context.set_prop_section
      section.needed_glue.add(field.type_defn)
      if 'userglue_setter' in field.attributes:
        glue_func = self.GetUserGlueSetterFunc(scope, type_defn, field)
        param_exprs = ['object', param_expr]
        if 'plugin_data' in field.attributes:
          self.AddPluginDataParam(scope, glue_func, param_exprs)
        self.GenerateCppFunction(context.header_section, scope, glue_func)
        expression = globals_binding.CppCallStaticMethod(scope, scope,
                                                         glue_func, param_exprs)
      else:
        expression = binding_model.CppSetField(scope, type_defn, 'object',
                                               field, param_expr)
      strings = [start_exception, code, _failure_test_string,
          '%s;' % expression, 'return true;', end_exception]
      self.EmitPropertyCode(section, prop_name,
                            '\n'.join(strings))

  def EmitStaticMemberProp(self, context, field):
    """Emits the glue for a static field access.

    Args:
      context: the code generation context.
      field: the field to access.
    """
    scope = context.scope
    type_defn = context.type_defn
    binding_model = context.binding_model
    id_enum = 'STATIC_PROPERTY_%s' % naming.Normalize(field.name, naming.Upper)
    prop_name = '"%s"' % naming.Normalize(field.name, naming.Java)
    has_prop_glue = "if (property==""%s"") return true;" % prop_name
    get_all_prop_names_glue_code = "names->push_back(\"%s\");" % prop_name
    context.static_prop_ids.append((id_enum, prop_name))

    section = context.static_has_prop_section
    section.EmitCode(has_prop_glue);
    section = context.static_get_all_property_names_section
    sectuin.EmitCode(get_all_prop_names_glue_code)
    if 'getter' in field.attributes:
      expression = binding_model.CppGetStatic(scope, type_defn, field)
      pre, post, needed_glue = self.GetReturnStrings(scope, field.type_defn,
                                                     expression, 'result')
    else:
      # Return a void value for write-only members.
      pre, post, needed_glue = self.GetVoidReturnStrings(field.type_defn,
                                                         'result')
    section = context.static_get_prop_section
    section.needed_glue.update(needed_glue)
    get_string = '\n'.join([pre, _failure_test_string, post, 'return true;'])
    self.EmitPropertyCode(section, prop_name,
                          get_string)

    if 'setter' in field.attributes:
      # TODO: Add a specific error for trying to set a read-only prop.
      field_binding = field.type_defn.binding_model
      start_exception, end_exception = GenExceptionContext(
          _exception_macro_name, "field",
          naming.Normalize(field.name, naming.Java))
      code, param_expr = field_binding.PpapiFromPPVar(
          scope, field.type_defn, 'value', 'param_%s' % field.name,
          'success', _exception_macro_name, 'instance')
      section = context.static_set_prop_section
      section.needed_glue.add(field.type_defn)
      expression = binding_model.CppSetStatic(scope, type_defn, field,
                                              param_expr)
      strings = [start_exception, code, _failure_test_string,
          '%s;' % expression, 'return true;', end_exception]
      self.EmitPropertyCode(section, prop_name,
                            '\n'.join(strings))

  def EmitEnumValue(self, context, enum, enum_value):
    """Emits the glue for an enum value access.

    Args:
      context: the code generation context.
      enum: the enum definition.
      enum_value: the enum value to access.
    """
    enum = enum  # silence gpylint.
    scope = context.scope
    type_defn = context.type_defn
    name = naming.Normalize(enum_value.name, naming.Upper)
    id_enum = 'ENUM_%s' % name
    prop_name = '"%s"' % name
    context.static_prop_ids.append((id_enum, prop_name))
    has_glue_code = "if (property==\"%s\") return true;" % enum_value.name
    get_all_prop_names_glue_code = "names->push_back(\"%s\");" % enum_value.name
    namespace = cpp_utils.GetScopedName(scope, type_defn)
    
    section = context.static_get_prop_section
    section.EmitCode(_enum_template.substitute(Enum=enum_value.name,
                                               Namespace=namespace))
    section = context.static_has_prop_section
    section.EmitCode(has_glue_code)
    section = context.static_get_all_property_names_section
    section.EmitCode(get_all_prop_names_glue_code)

  def EmitCallCode(self, section, name, arg_count, code):
    """Emits glue code in an 'Invoke' dispatch function.

    Args:
      section: the code section of the dispatch function.
      table: the table in which the method identifier is defined.
      id_enum: the method identifier enum.
      arg_count: the number of arguments for the function.
      code: the glue code.
    """
    section.EmitCode(_method_call_template.substitute(method_name=name,
                                                      argCount=arg_count,
                                                      code=code))

  def EmitInvokeDefaultCode(self, section, arg_count, code):
    """Emits glue code in an 'InvokeDefault' dispatch function.

    Args:
      section: the code section of the dispatch function.
      arg_count: the number of arguments for the function.
      code: the glue code.
    """
    section.EmitCode(_method_default_invoke_template.substitute(
        argCount=arg_count, code=code))

  def EmitPropertyCode(self, section, name_quoted, code):
    """Emits glue code in a 'GetProperty' or 'SetProperty' dispatch function.

    Args:
      section: the code section of the dispatch function.
      table: the table in which the property identifier is defined.
      id_enum: the property identifier enum.
      code: the glue code.
    """
    section.EmitCode(_property_template.substitute(Name=name_quoted,
                                                   code=code))

  def Variable(self, context, obj):
    """Emits the glue code for a Variable definition.

    Args:
      context: the code generation context.
      obj: the Variable definition.
    """
    if 'private' in obj.attributes or 'protected' in obj.attributes:
      return
    if 'static' in obj.attributes or context.is_namespace:
      self.EmitStaticMemberProp(context, obj)
    else:
      self.EmitMemberProp(context, obj)

  def Enum(self, context, obj):
    """Emits the glue code for an Enum definition.

    Args:
      context: the code generation context.
      obj: the Enum definition.
    """
    if 'private' in obj.attributes or 'protected' in obj.attributes:
      return
    for value in obj.values:
      self.EmitEnumValue(context, obj, value)

  def Function(self, context, obj):
    """Emits the glue code for a Function definition.

    Args:
      context: the code generation context.
      obj: the Function definition.

    Raises:
      MethodWithoutReturnType: a non-constructor function doesn't have a return
        type.
    """
    if 'private' in obj.attributes or 'protected' in obj.attributes:
      return
    if 'static' in obj.attributes or context.is_namespace:
      self.EmitStaticCall(context, obj)
    else:
      if not obj.type_defn:
        if obj.name == context.type_defn.name:
          # constructor
          self.EmitConstructorCall(context, obj)
        elif obj.name == '~' + context.type_defn.name:
          # destructor (ignore)
          return
        else:
          # method without return type: error
          raise MethodWithoutReturnType(obj)
      else:
        self.EmitMemberCall(context, obj)

  def Callback(self, context, obj):
    """Emits the glue code for a Callback definition.

    Args:
      context: the code generation context.
      obj: the Callback definition.
    """
    if 'private' in obj.attributes or 'protected' in obj.attributes:
      return

    binding_model = obj.binding_model
    namespace_name = npapi_utils.GetGlueNamespace(obj)

    scope = syntax_tree.Namespace(None, [], namespace_name, [])
    scope.parent = context.scope

    context.header_section.PushNamespace(namespace_name)
    header_section = context.header_section.CreateSection(namespace_name)
    header_section.needed_defn = context.header_section.needed_defn
    header_section.needed_glue = context.header_section.needed_glue
    header_section.additional_includes = (
        context.header_section.additional_includes)
    context.header_section.PopNamespace()

    context.cpp_section.PushNamespace(namespace_name)
    cpp_section = context.cpp_section.CreateSection(namespace_name)
    cpp_section.needed_glue = context.cpp_section.needed_glue
    context.cpp_section.PopNamespace()

    param_to_variant_pre = []
    param_to_variant_post = []
    param_strings = []
    for i in xrange(len(obj.params)):
      p = obj.params[i]
      param_string, unused_val = cpp_utils.GetFunctionParamPrototype(scope, p)
      header_section.needed_defn.add(p.type_defn)
      cpp_section.needed_glue.add(p.type_defn)
      param_strings += [param_string]
      bm = p.type_defn.binding_model
      pre, post = bm.PpapiExprToPPVar(scope, p.type_defn, 'var_' + p.name,
                                      p.name, '(args + %d)' % i, 'success',
                                      'instance')
      param_to_variant_pre.append(pre)
      param_to_variant_post.append(post)

    if param_strings:
      param_strings = [''] + param_strings

    return_type = obj.type_defn
    header_section.needed_defn.add(return_type)
    cpp_section.needed_glue.add(return_type)
    bm = return_type.binding_model
    return_type_string, unused_val = bm.CppReturnValueString(scope,
                                                             return_type)
    run_callback = (('%s RunCallback(pp::InstancePrivate* instance, '
                     'pp::Var& object, bool async%s)')
                    % (return_type_string, ', '.join(param_strings)))

    return_eval, return_value = bm.PpapiFromPPVar(scope, return_type,
                                                  'result', 'retval',
                                                  'success',
                                                  _exception_macro_name,
                                                  'instance')
    start_exception, end_exception = GenExceptionContext(
        _exception_macro_name, "callback return value", "<no name>")
    subst_dict = {'RunCallback': run_callback,
                  'ArgCount': str(len(obj.params)),
                  'ParamsToVariantsPre': '\n'.join(param_to_variant_pre),
                  'ParamsToVariantsPost': '\n'.join(param_to_variant_post),
                  'ReturnEval': return_eval,
                  'ReturnValue': return_value,
                  'StartException': start_exception,
                  'EndException': end_exception}
    if obj.params:
      glue_template = _callback_glue_cpp_template
    else:
      glue_template = _callback_no_param_glue_cpp_template
    cpp_section.EmitCode(glue_template.substitute(subst_dict))
    cpp_section.EmitCode(binding_model.PpapiBindingGlueCpp(scope, obj))
    header_section.EmitCode(binding_model.PpapiBindingGlueHeader(scope, obj))

  def GetDictForEnumerations(self, context, has_base):
    """Creates a dictionary used to fill in the gaps in the property
    enumeration functions.  Note that this dictionary will in some cases cause
    the insertion of the string ${BaseClassNamespace}, so it must be used
    *before* the dictionary that fills in that macro.  This only happens when
    the context is a derived class.

    Args:
      context: the code generation context
      has_base: whether this is a class that has a base class

    Returns:
      a dictionary containing definitions for the code generation templates
    """
    dict = {}
    return dict

  def Class(self, parent_context, obj):
    """Emits the glue code for a Class definition.

    Args:
      parent_context: the code generation context.
      obj: the Class definition.
    """
    if 'private' in obj.attributes or 'protected' in obj.attributes:
      return

    binding_model = obj.binding_model

    namespace_name = npapi_utils.GetGlueNamespace(obj)
    parent_context.namespace_list.append(obj)

    scope = syntax_tree.Namespace(None, [], namespace_name, [])
    scope.parent = parent_context.scope

    parent_context.header_section.PushNamespace(namespace_name)
    header_section = parent_context.header_section.CreateSection(namespace_name)
    header_section.needed_defn = parent_context.header_section.needed_defn
    header_section.needed_glue = parent_context.header_section.needed_glue
    header_section.additional_includes = (
        parent_context.header_section.additional_includes)
    parent_context.header_section.PopNamespace()

    parent_context.cpp_section.PushNamespace(namespace_name)
    cpp_section = parent_context.cpp_section.CreateSection(namespace_name)
    cpp_section.needed_glue = parent_context.cpp_section.needed_glue
    parent_context.cpp_section.PopNamespace()

    context = self.CodeGenContext(obj, scope, header_section, cpp_section, None)
    header_section.needed_defn.add(obj)
    cpp_section.needed_glue.add(obj)

    self.GenerateList(context, obj.defn_list)

    class_name_list = naming.SplitWords(obj.name)
    class_capitalized = naming.Capitalized(class_name_list)
    class_param_type, unused_need_defn = binding_model.CppParameterString(scope,
                                                                          obj)
    class_mutable_param_type, unused_need_defn = (
        binding_model.CppMutableParameterString(scope, obj))
    binding_glue_header, binding_glue_includes, binding_glue_base_class = (
        binding_model.PpapiBindingGlueHeader(scope, obj))
    binding_glue_cpp = binding_model.PpapiBindingGlueCpp(scope, obj)
    function_header, object_access = binding_model.PpapiDispatchFunctionHeader(
        scope, obj, 'object', 'npp', 'success')
    object_non_mutable = binding_model.CppMutableToNonMutable(scope, obj,
                                                              object_access)
    type_defn = context.type_defn
    class_scoped_name = cpp_utils.GetScopedName(scope, type_defn)

    static_dict = {'Class': class_capitalized,
                   'ClassParamType': class_param_type,
                   'ClassScopedName': class_scoped_name,
                   'ClassMutableParamType': class_mutable_param_type,
                   'Object': object_access,
                   'ObjectNonMutable': object_non_mutable,
                   'BindingGlueCpp': binding_glue_cpp,
                   'BindingGlueHeader': binding_glue_header,
                   'BindingGlueBaseClass' : binding_glue_base_class,
                   'DispatchFunctionHeader': function_header}

    if binding_glue_includes:
      header_section.additional_includes.add(binding_glue_includes)

    enum_dict = self.GetDictForEnumerations(context, obj.base_type)
    if obj.base_type:
      parent_context.cpp_section.needed_glue.add(obj.base_type)
      header_section.needed_glue.add(obj.base_type)
      base_namespace = npapi_utils.GetGlueFullNamespace(
          obj.base_type.GetFinalType())
      static_dict['BaseClassNamespace'] = base_namespace
      cpp_template = _class_glue_cpp_base_template.safe_substitute(enum_dict)
      header_template = _class_glue_header_base_template
    else:
      cpp_template = _class_glue_cpp_no_base_template.safe_substitute(enum_dict)
      header_template = _class_glue_header_no_base_template

    cpp_template = string.Template(cpp_template).safe_substitute(static_dict)

    header_section.EmitCode(header_template.safe_substitute(static_dict))

    namespace_id_dict = GenNamespaceCode(context)
    parent_context.cpp_section.needed_glue.update(context.namespace_list)
    substitution_dict = {}
    substitution_dict.update(npapi_utils.MakeIdTableDict(
        context.method_ids, 'method'))
    substitution_dict.update(npapi_utils.MakeIdTableDict(
        context.static_method_ids, 'static_method'))
    substitution_dict.update(npapi_utils.MakeIdTableDict(
        context.prop_ids, 'property'))
    substitution_dict.update(npapi_utils.MakeIdTableDict(
        context.static_prop_ids, 'static_property'))
    substitution_dict.update(namespace_id_dict)

    cpp_section.EmitTemplate(string.Template(cpp_template).safe_substitute(
        substitution_dict))

  def Verbatim(self, context, obj):
    """Emits the glue code for a Verbatim definition.

    Args:
      context: the code generation context.
      obj: the Verbatim definition.
    """
    if 'verbatim' in obj.attributes:
      if obj.attributes['verbatim'] == 'cpp_glue':
        context.cpp_section.EmitCode(obj.text)
      elif obj.attributes['verbatim'] == 'header_glue':
        context.header_section.EmitCode(obj.text)

  def Namespace(self, parent_context, obj):
    """Emits the glue code for a Namespace definition.

    Since a namespace can be defined through several Namespace definitions,
    this function doesn't generate all the glue for the namespace until all the
    namespaces definitions have been processed (second pass).

    Args:
      parent_context: the code generation context.
      obj: the Namespace definition.
    """
    namespace_name = npapi_utils.GetGlueNamespace(obj)
    # namespaces that span across multiple files are different objects
    # we keep definitions inside the namespace separate, but all the 'static'
    # glue needs to be gathered. So we create a code generation context that
    # will be re-used when a different part of the namespace will be
    # encountered
    # all the different namespaces share the same scope member, so use that as
    # a key into a dict that maps the context
    if obj.scope in self._namespace_map:
      old_context = self._namespace_map[obj.scope]

      parent_context.header_section.PushNamespace(namespace_name)
      header_section = parent_context.header_section.CreateSection(
          namespace_name)
      header_section.needed_defn = parent_context.header_section.needed_defn
      header_section.needed_glue = parent_context.header_section.needed_glue
      header_section.additional_includes = (
          parent_context.header_section.additional_includes)
      parent_context.header_section.PopNamespace()

      parent_context.cpp_section.PushNamespace(namespace_name)
      cpp_section = parent_context.cpp_section.CreateSection(namespace_name)
      cpp_section.needed_glue = parent_context.cpp_section.needed_glue
      parent_context.cpp_section.PopNamespace()

      context = self.CodeGenContext(old_context.type_defn, old_context.scope,
                                    header_section, cpp_section, old_context)
    else:
      parent_context.namespace_list.append(obj)

      scope = syntax_tree.Namespace(None, [], namespace_name, [])
      scope.parent = parent_context.scope

      parent_context.header_section.PushNamespace(namespace_name)
      header_section = parent_context.header_section.CreateSection(
          namespace_name)
      header_section.needed_defn = parent_context.header_section.needed_defn
      header_section.needed_glue = parent_context.header_section.needed_glue
      header_section.additional_includes = (
          parent_context.header_section.additional_includes)
      parent_context.header_section.PopNamespace()

      parent_context.cpp_section.PushNamespace(namespace_name)
      cpp_section = parent_context.cpp_section.CreateSection(namespace_name)
      cpp_section.needed_glue = parent_context.cpp_section.needed_glue
      parent_context.cpp_section.PopNamespace()

      context = self.CodeGenContext(obj, scope, header_section,
                                    cpp_section, None)
      self._namespace_map[obj.scope] = context

      def _Finalize():
        # This part can only be finalized after all files have been processed,
        # because later files can still add definitions to the namespace.
        # So do this work in a function that will get called at the end.
        namespace_id_dict = GenNamespaceCode(context)
        parent_context.cpp_section.needed_glue.update(context.namespace_list)

        substitution_dict = {}
        substitution_dict.update(npapi_utils.MakeIdTableDict(
            context.static_method_ids, 'static_method'))
        substitution_dict.update(npapi_utils.MakeIdTableDict(
            context.static_prop_ids, 'static_property'))
        substitution_dict.update(namespace_id_dict)

        header_section.EmitCode(_namespace_glue_header)

        enum_dict = self.GetDictForEnumerations(context, False)
        temp_string = _namespace_glue_cpp_template.safe_substitute(enum_dict)
        temp_template = string.Template(temp_string)

        cpp_section.EmitTemplate(temp_template.safe_substitute(
            substitution_dict))

      self._finalize_functions.append(_Finalize)

    context.cpp_section.needed_glue.add(obj)
    self.GenerateList(context, obj.defn_list)

  def Typedef(self, context, obj):
    """Emits the glue code for a Typedef definition.

    Args:
      context: the code generation context.
      obj: the Typedef definition.
    """
    # TODO: implement this.
    pass

  def Typename(self, context, obj):
    """Emits the glue code for a Typename definition.

    Typename being unknown types, no glue is generated for them.

    Args:
      context: the code generation context.
      obj: the Typename definition.
    """
    pass

  def GenerateList(self, context, defn_list):
    """Emits the glue code for a list of definitions.

    Args:
      context: the code generation context.
      defn_list: the definition list.
    """
    for obj in defn_list:
      if 'nojs' in obj.attributes:
        continue
      if 'include' in obj.attributes:
        context.header_section.needed_defn.add(obj)
      func = getattr(self, obj.defn_type)
      func(context, obj)

  def CreateGlueWriters(self, idl_file):
    """Creates CppFileWriter instances for glue header and implementation.

    Args:
      idl_file: an idl_parser.File for the source file.

    Returns:
      a pair of CppFileWriter, the first being the glue header writer, the
      second one being the glue implementation writer.
    """
    cpp_writer = cpp_utils.CppFileWriter(
        '%s/%s' % (self._output_dir, GetGlueCpp(idl_file)), False)
    for include, system in _cpp_includes:
      cpp_writer.AddInclude(include, system)
    cpp_writer.AddInclude(GetGlueHeader(idl_file), False)

    header_writer = cpp_utils.CppFileWriter(
        '%s/%s' % (self._output_dir, GetGlueHeader(idl_file)), True)
    for include, system in _header_includes:
      header_writer.AddInclude(include, system)
    return header_writer, cpp_writer

  def CreateGlueSection(self, writer):
    """Utility function to create a 'glue' section in a writer.

    This function will create a new section inside a 'glue' namespace.

    Args:
      writer: a CppFileWriter in which to create the section.

    Returns:
      the created section.
    """
    writer.PushNamespace('glue')
    section = writer.CreateSection('glue')
    writer.PopNamespace()
    return section

  def BeginFile(self, idl_file, parent_context, defn_list):
    """Runs the pass 1 generation for an IDL file.

    Args:
      idl_file: the source IDL file.
      parent_context: the code generation context.
      defn_list: the list of top-level definitions in the IDL file.

    Returns:
      a 3-uple. The first element is the code generation context for that file.
      The second element is the glue header writer. The third element is the
      glue implementation writer.
    """
    header_writer, cpp_writer = self.CreateGlueWriters(idl_file)
    header_writer.needed_defn = set()
    cpp_writer.needed_glue = set()
    header_writer.needed_glue = set()
    header_writer.additional_includes = set()

    header_section = self.CreateGlueSection(header_writer)
    cpp_section = self.CreateGlueSection(cpp_writer)
    header_section.needed_defn = header_writer.needed_defn
    cpp_section.needed_glue = cpp_writer.needed_glue
    header_section.needed_glue = header_writer.needed_glue
    header_section.additional_includes = header_writer.additional_includes

    context = self.CodeGenContext(parent_context.type_defn,
                                  parent_context.scope, header_section,
                                  cpp_section, parent_context)

    self.GenerateList(context, defn_list)
    return context, header_writer, cpp_writer

  def FinishFile(self, idl_file, context, header_writer, cpp_writer):
    """Runs the pass 2 generation for an IDL file.

    Args:
      idl_file: the source IDL file.
      context: the code generation context for this file (returned by
        BeginFile)
      header_writer: the glue header writer (returned by BeginFile).
      cpp_writer: the glue implementation writer (returned by BeginFile).

    Returns:
      a list of CppFileWriter instances that contain the generated files.
    """
    context = context  # silence gpylint
    source_files = (type_defn.GetFinalType().source.file for type_defn in
                    cpp_writer.needed_glue)
    cpp_needed_glue_includes = set(GetGlueHeader(source_file) for source_file
                                   in source_files)
    cpp_needed_glue_includes.add(GetGlueHeader(idl_file))

    for include_file in cpp_needed_glue_includes:
      if include_file:
        cpp_writer.AddInclude(include_file)

    for include_file in set(type_defn.GetDefinitionInclude() for type_defn
                            in header_writer.needed_defn):
      if include_file:
        header_writer.AddInclude(include_file)

    source_files = (type_defn.GetFinalType().source.file for type_defn in
                    header_writer.needed_glue)
    header_needed_glue_includes = set(GetGlueHeader(source_file) for source_file
                                      in source_files)
    for include_file in header_needed_glue_includes:
      if include_file:
        # TODO(jhorwich) Avoid adding include if the include is the
        # same file as the file being written. Right now this is harmless
        # due to header guards but it is sloppy
        header_writer.AddInclude(include_file)

    for include_file in header_writer.additional_includes:
      header_writer.AddInclude(include_file)

    return [header_writer, cpp_writer]

  def BeginGlobals(self, idl_file, namespace):
    """Runs the pass 1 generation for the global namespace.

    A separate files are written containing the global namespace glue.

    Args:
      idl_file: an idl_file.File for the global namespace file.
      namespace: the global namespace.

    Returns:
      a 3-uple. The first element is the code generation context for that file.
      The second element is the glue header writer. The third element is the
      glue implementation writer.
    """
    scope = syntax_tree.Namespace(None, [], 'glue', [])
    scope.parent = namespace

    header_writer, cpp_writer = self.CreateGlueWriters(idl_file)
    header_writer.needed_defn = set()
    cpp_writer.needed_glue = set()
    header_writer.needed_glue = set()
    header_section = self.CreateGlueSection(header_writer)
    cpp_section = self.CreateGlueSection(cpp_writer)
    header_section.needed_defn = header_writer.needed_defn
    cpp_section.needed_glue = cpp_writer.needed_glue
    header_section.needed_glue = header_writer.needed_glue

    context = self.CodeGenContext(namespace, scope, header_section,
                                  cpp_section, None)
    return context, header_writer, cpp_writer

  def FinishGlobals(self, context, header_writer, cpp_writer):
    """Runs the pass 2 generation for the global namespace.

    Args:
      context: the code generation context for the global namespace (returned
        by BeginGlobals).
      header_writer: the glue header writer (returned by BeginGlobals).
      cpp_writer: the glue implementation writer (returned by BeginGlobals).

    Returns:
      a list of CppFileWriter instances that contain the generated files.
    """
    for f in self._finalize_functions:
      f()
    namespace_id_dict = GenNamespaceCode(context)

    substitution_dict = {}
    substitution_dict.update(npapi_utils.MakeIdTableDict(
        context.static_method_ids, 'static_method'))
    substitution_dict.update(npapi_utils.MakeIdTableDict(
        context.static_prop_ids, 'static_property'))
    substitution_dict.update(namespace_id_dict)

    context.header_section.EmitCode(_namespace_glue_header)

    enum_dict = self.GetDictForEnumerations(context, False)
    temp_string = _namespace_glue_cpp_template.safe_substitute(enum_dict)
    temp_template = string.Template(temp_string)

    context.cpp_section.EmitTemplate(
        temp_template.safe_substitute(substitution_dict))

    includes = set(GetGlueHeader(ns_obj.source.file) for ns_obj in
                   context.namespace_list)

    for include_file in includes:
      if include_file is not None:
        cpp_writer.AddInclude(include_file)

    return [header_writer, cpp_writer]


def ProcessFiles(output_dir, pairs, namespace):
  """Generates the PPAPI glue for all input files.

  Args:
    output_dir: the output directory.
    pairs: a list of (idl_parser.File, syntax_tree.Definition list) describing
      the list of top-level definitions in each source file.
    namespace: a syntax_tree.Namespace for the global namespace.

  Returns:
    a list of cpp_utils.CppFileWriter, one for each output glue header or
    implementation file.
  """
  globals_file = idl_parser.File('<internal>')
  globals_file.header = None
  globals_file.basename = 'globals'
  generator = PpapiGenerator(output_dir)

  # pass 1
  global_context, global_header_writer, global_cpp_writer = (
      generator.BeginGlobals(globals_file, namespace))
  file_map = {}
  for (idl_file, defn) in pairs:
    context, header_writer, cpp_writer = generator.BeginFile(
        idl_file, global_context, defn)
    file_map[idl_file] = (context, header_writer, cpp_writer)

  # pass 2
  writer_list = generator.FinishGlobals(global_context, global_header_writer,
                                        global_cpp_writer)
  for (idl_file, defn) in pairs:
    context, header_writer, cpp_writer = file_map[idl_file]
    writer_list += generator.FinishFile(idl_file, context, header_writer,
                                        cpp_writer)
  return writer_list


def main():
  pass

if __name__ == '__main__':
  main()
