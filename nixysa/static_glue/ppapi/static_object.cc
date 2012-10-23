/*
 * Copyright 2011, Google Inc.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met:
 *
 *     * Redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above
 * copyright notice, this list of conditions and the following disclaimer
 * in the documentation and/or other materials provided with the
 * distribution.
 *     * Neither the name of Google Inc. nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#include "static_object.h"

#include "ppapi/cpp/private/var_private.h"
#include "ppapi/cpp/var.h"

namespace glue {
namespace globals {

StaticObject::StaticObject()
    : base_class_(NULL) {
}

StaticObject::~StaticObject() {
}

void StaticObject::SetBaseClass(StaticObject* base_class) {
  base_class_ = base_class;
}

void StaticObject::AddNamespaceObject(const std::string& name,
                                      StaticObject* object) {
  namespace_objects_[name] = object;
}

StaticObject* StaticObject::GetNamespaceObject(
    const std::string& namespace_name) {
  NamespaceObjectMap::const_iterator it =
       namespace_objects_.find(namespace_name);
  if (it != namespace_objects_.end())
    return it->second;
  else
    return NULL;
}

void StaticObject::RegisterObjectBases(StaticObject* root_object) {
}

void StaticObject::RegisterObjectWrappers(pp::InstancePrivate* instance) {
}

StaticObject* StaticObject::GetStaticObject(StaticObject* root_object) {
  return root_object;
}

bool StaticObject::HasMethodInner(const std::string method) {
  if (base_class_)
    return base_class_->HasMethodInner(method);
  return false;
}

bool StaticObject::HasPropertyInner(const std::string property) {
  NamespaceObjectMap::const_iterator it = namespace_objects_.find(property);
  if (it != namespace_objects_.end())
    return true;
  if (base_class_)
    return base_class_->HasPropertyInner(property);
  return false;
}

bool StaticObject::GetPropertyInner(pp::InstancePrivate* instance,
                                    const std::string property,
                                    pp::Var* exception,
                                    pp::Var* result) {
  NamespaceObjectMap::const_iterator it = namespace_objects_.find(property);
  if (it != namespace_objects_.end()) {
    *result = pp::VarPrivate(instance, it->second->CreateWrapper(instance));
    return true;
  }
  if (base_class_)
    return base_class_->GetPropertyInner(instance, property, exception, result);
  if (exception->is_null())
    *exception = pp::Var("unknown property");
  return false;
}

void StaticObject::GetAllPropertyNames(std::vector<pp::Var>* names,
                                       pp::Var* exception) {
  if (base_class_)
    base_class_->GetAllPropertyNames(names, exception);
}

bool StaticObject::SetPropertyInner(const std::string name,
                                    const pp::Var& value,
                                    pp::Var* exception) {
  if (base_class_)
    return base_class_->SetPropertyInner(name, value, exception);
  if (exception->is_null())
    *exception = pp::Var("unknown property");
  return false;
}

bool StaticObject::CallInner(pp::InstancePrivate* instance,
                             const std::string method,
                             const std::vector<pp::Var>& args,
                             pp::Var* exception,
                             pp::Var* result) {
  if (base_class_)
    return base_class_->CallInner(instance, method, args, exception, result);
  if (exception->is_null())
    *exception = pp::Var("method does not exist");
  return false;
}

bool StaticObject::ConstructInner(pp::InstancePrivate* instance,
                                  const std::vector<pp::Var>& args,
                                  pp::Var* exception,
                                  pp::Var* result) {
  *exception = pp::Var("missing constructor");
  return false;
}

StaticObjectWrapper* StaticObject::CreateWrapper(
    pp::InstancePrivate* instance) {
  return new StaticObjectWrapper(instance, this);
}

StaticObjectWrapper::StaticObjectWrapper(pp::InstancePrivate* instance,
                                         StaticObject* static_object)
      : pp::deprecated::ScriptableObject(),
        instance_(instance),
        static_object_(static_object) {
}

bool StaticObjectWrapper::HasMethod(const pp::Var& method, pp::Var* exception) {
  if (method.is_string())
    return static_object_->HasMethodInner(method.AsString());
  *exception = pp::Var("method name is not a string");
  return false;
}

bool StaticObjectWrapper::HasProperty(const pp::Var& name, pp::Var* exception) {
  if (name.is_string())
    return static_object_->HasPropertyInner(name.AsString());
  *exception = pp::Var("property name is not a string");
  return false;
}

pp::Var StaticObjectWrapper::GetProperty(const pp::Var& name,
                                         pp::Var* exception) {
  pp::Var result = pp::Var();
  if (!name.is_string()) {
    *exception = pp::Var("property name is not a string");
    return result;
  }
  static_object_->GetPropertyInner(plugin_instance(),
                                   name.AsString(),
                                   exception,
                                   &result);
  return result;
}

void StaticObjectWrapper::GetAllPropertyNames(std::vector<pp::Var>* names,
                                              pp::Var* exception) {
  static_object_->GetAllPropertyNames(names, exception);
}

void StaticObjectWrapper::SetProperty(const pp::Var& name,
                                      const pp::Var& value,
                                      pp::Var* exception) {
  if (name.is_string())
    static_object_->SetPropertyInner(name.AsString(), value, exception);
  else
    *exception = pp::Var("property name is not a string");
}

pp::Var StaticObjectWrapper::Call(const pp::Var& method,
                                  const std::vector<pp::Var>& args,
                                  pp::Var* exception) {
  pp::Var result = pp::Var();
  if (method.is_undefined()) {
    return Construct(args, exception);
  }
  if (!method.is_string()) {
    *exception = pp::Var("method name is not a string");
    return result;
  }
  static_object_->CallInner(plugin_instance(),
                            method.AsString(),
                            args,
                            exception,
                            &result);
  return result;
}

pp::Var StaticObjectWrapper::Construct(const std::vector<pp::Var>& args,
                                       pp::Var* exception) {
  pp::Var result = pp::Var();
  static_object_->ConstructInner(plugin_instance(), args, exception, &result);
  return result;
}

}  // namespace globals
}  // namespace glue
