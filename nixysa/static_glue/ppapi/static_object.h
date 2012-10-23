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

#ifndef NIXYSA_STATIC_GLUE_PPAPI_STATIC_OBJECT_H_
#define NIXYSA_STATIC_GLUE_PPAPI_STATIC_OBJECT_H_

#include <string>
#include <vector>

#include "base/hash_tables.h"
#include "ppapi/cpp/dev/scriptable_object_deprecated.h"
#include "ppapi/cpp/private/instance_private.h"
#include "ppapi/cpp/var.h"

namespace glue {
namespace globals {

class StaticObjectWrapper;

class StaticObject {
  typedef ::base::hash_map<std::string, StaticObject*> NamespaceObjectMap;

 public:
  StaticObject();
  virtual ~StaticObject();
  void SetBaseClass(StaticObject* base_class);
  void AddNamespaceObject(const std::string& name, StaticObject* object);
  StaticObject* GetNamespaceObject(const std::string& namespace_name);
  virtual void RegisterObjectBases(StaticObject* root_object);
  virtual void RegisterObjectWrappers(pp::InstancePrivate* instance);
  static StaticObject* GetStaticObject(StaticObject* root_object);
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
  virtual StaticObjectWrapper* CreateWrapper(pp::InstancePrivate *instance);

 private:
  StaticObject* base_class_;
  NamespaceObjectMap namespace_objects_;

  // Commented out since we don't have base/basictypes.h in NIXYSA,
  // but we would like to discourage copying and assignment
  //DISALLOW_COPY_AND_ASSIGN(StaticObject);
};

class StaticObjectWrapper : public pp::deprecated::ScriptableObject {
 public:
  StaticObjectWrapper(pp::InstancePrivate* instance,
                      StaticObject* static_object);
  virtual bool HasMethod(const pp::Var& method, pp::Var* exception);
  virtual bool HasProperty(const pp::Var& name, pp::Var* exception);
  virtual pp::Var GetProperty(const pp::Var& name, pp::Var* exception);
  virtual void GetAllPropertyNames(std::vector<pp::Var>* names,
                                   pp::Var* exception);
  virtual void SetProperty(const pp::Var& name, const pp::Var& value,
                           pp::Var* exception);
  virtual pp::Var Call(const pp::Var& method,
                       const std::vector<pp::Var>& args,
                       pp::Var* exception);
  virtual pp::Var Construct(const std::vector<pp::Var>& args,
                            pp::Var* exception);
  pp::InstancePrivate* plugin_instance() { return (instance_); }

 private:
  pp::InstancePrivate* instance_;
  StaticObject* static_object_;

  // Commented out since we don't have base/basictypes.h in NIXYSA,
  // but we would like to discourage copying and assignment
  //DISALLOW_COPY_AND_ASSIGN(StaticObjectWrapper);
};

}  // namespace globals
}  // namespace glue

#endif  // NIXYSA_STATIC_GLUE_PPAPI_STATIC_OBJECT_H_
