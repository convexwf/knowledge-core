---
description: Coding general (10) - cross-language standards; use 11-19 for per-language rules
alwaysApply: false
---

# Coding: General (10) and per-language (11–19)

- **10-** = **General coding** rules (cross-language or shared conventions).
- **11–19** = **Per-language** rules. Use one rule file per language, e.g. `11-coding-python.mdc`, `12-coding-typescript.mdc`.

- **Current status:** Placeholder. Add 10- rules for shared standards and 11-19 rules when defining language-specific conventions.
- **When adding:** Create the `.mdc` in `.cursor/rules/`, and add or update the backup in `doc/rules/10-coding.md` (one file per category; English only).

## Rule: 11-coding-go.mdc

---
description: Go (11) – binaries in bin/, build then run; no go run in scripts
globs: "**/*.go"
alwaysApply: false
---

# Go: build and run (11)

## Binaries in bin/

- **All compiled binaries must go in `bin/`.** Never build to project root or other directories. Use: `go build -o bin/<name> ./cmd/<name>`. Do not run `go build ./cmd/...` without `-o bin/...`.

## Build then run

- **For every runnable (server, seed, or any future cmd): always build then run.** In scripts, Makefile, and documentation, do **not** use `go run ./cmd/...`. Build the binary (e.g. `make build` / `make build-seed` or `go build -o bin/<name> ./cmd/<name>`) and then run `./bin/<name>`. This applies to server, seed, and any other command added later.

## Rule: 12-coding-godot.mdc

---
description: Godot 4.5 / GDExtension C++ – naming, GDCLASS, Docker build, register_types, etc.
globs: "**/*.cpp"
alwaysApply: false
---

# Godot 4.5 / GDExtension C++ (12)

You are a Godot 4.5 expert specializing in GDExtension C++ development. Follow godot-cpp standards and best practices. Do NOT provide GDScript code unless explicitly requested.

## Technology Stack

- **Engine**: Godot 4.5+
- **Language**: C++20
- **Compiler**: Clang 17 (for local IDE), platform-specific in Docker
- **Build Tool**: SCons (runs in Docker containers via `scripts/build/build.sh`)
- **Library**: godot-cpp bindings
- **Build System**: Docker-based cross-platform compilation

## Code Style and Conventions

### Naming

- **Classes**: `PascalCase` (e.g., `Player`, `BombController`)
- **Methods/Functions**: `snake_case` (e.g., `move_player()`, `get_health()`)
- **Variables**: `snake_case` (e.g., `move_speed`, `bomb_count`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_BOMBS`)
- **File names**: Match class name in lowercase (e.g., `Player` → `player.h`)

### Type Usage

- **Prefer Godot types over STL**: Use `godot::String`, `godot::Vector2`, `godot::Dictionary`, `godot::Array` instead of `std::string`, `std::vector`, `std::map`
- **Exception**: STL is acceptable for internal algorithms or performance-critical code not exposed to Godot

### Code Structure

- One class per file pair (`*.h` and `*.cpp`)
- Always use `GDCLASS(ClassName, BaseClass)` macro in class definition
- Declare `_bind_methods()` in `protected:` section
- Use `override` keyword for virtual method overrides
- Include proper header guards: `#ifndef CLASS_NAME_H` / `#define CLASS_NAME_H`

### Comments and Documentation

- **Code comments**: English only (mandatory)
- **Documentation files**: Must have both English and Chinese versions (English primary; Chinese with `.zh-cn` suffix per project doc rules)
- **Comment style**: Google C++ Style Guide
- **Function comments**: Doxygen-style for public APIs
- **Inline comments**: Explain "why", not "what"

## GDExtension Requirements

### Class Registration

- All classes must be registered in `src/register_types.cpp` using `ClassDB::register_class<ClassName>()`
- Include class header in `register_types.cpp`
- Registration happens in `initialize_example_module()` function

### Method Binding

- Methods exposed to GDScript must be bound in `_bind_methods()` using `ClassDB::bind_method(D_METHOD("method_name", "param1"), &ClassName::method_name)`
- Properties require getter/setter methods and `ClassDB::add_property()` call
- Signals use `ADD_SIGNAL(MethodInfo("signal_name", PropertyInfo(...)))`

### Module Initialization

- Entry function name must match `entry_symbol` in `.gdextension` file (typically `{project}_library_init`)
- Use `GDExtensionBinding::InitObject` for initialization
- Set minimum library initialization level (typically `MODULE_INITIALIZATION_LEVEL_SCENE`)

## Build System

### Important Rules

- **NEVER suggest local SCons installation** - all builds use Docker containers
- **Build commands**: Use `./scripts/build/build.sh <platform> [target]` (e.g., `./scripts/build/build.sh web template_debug`)
- **Development verification**: Use **web** as the target platform when validating GDExtension builds. This ensures the extension loads in the web export context.
- **Supported platforms**: `linuxbsd`, `windows`, `web`, `macos`, `android`
- **Build targets**: `template_debug`, `template_release`, `editor`
- **Output location**: `{project_name}/gdextension/{lib_name}.{platform}.{target}.{arch}.{ext}`. Project and library names are defined in `SConstruct` (`GODOT_PROJECT_NAME`, `GDEXTENSION_LIB_NAME`).
- **IDE support**: Generate `compile_commands.json` with `./scripts/build/utils/build_compile_json.sh <platform>` (use the platform you develop for, e.g. `web` for web-focused work)

### Project Structure

- Source files: `src/*.cpp`, `src/*.h`
- Build config: `SConstruct` (defines `GODOT_PROJECT_NAME` and `GDEXTENSION_LIB_NAME` - project-specific)
- GDExtension config: `{project_name}/gdextension/{extension_name}.gdextension` (project-specific paths)
- Library naming: Must match `.gdextension` file configuration and `GDEXTENSION_LIB_NAME` in `SConstruct`

## Code Generation Checklist

When generating a new class, ensure:

- [ ] Header file with include guards (`#ifndef CLASS_NAME_H`)
- [ ] `GDCLASS(ClassName, BaseClass)` macro in class definition
- [ ] `_bind_methods()` declared in `protected:` section
- [ ] Constructor and destructor implemented
- [ ] Implementation file includes class header
- [ ] `_bind_methods()` implementation (even if empty)
- [ ] Class registered in `src/register_types.cpp`
- [ ] Methods bound if needed for GDScript access
- [ ] Properties bound if needed
- [ ] Virtual methods marked with `override`
- [ ] English comments following Google style
- [ ] Uses Godot types, not STL (when appropriate)

## Common Mistakes to Avoid

1. Forgetting to register class in `register_types.cpp`
2. Not binding methods that need GDScript access
3. Using STL types when Godot types are more appropriate
4. Missing `GDCLASS` macro in class definition
5. Wrong naming convention (e.g., `camelCase` instead of `snake_case`)
6. Not including headers properly
7. Forgetting `override` keyword on virtual methods
8. Using wrong base class (check Godot API docs)
9. Suggesting local SCons installation
10. Not matching library name with `.gdextension` configuration

## Reference Files

When generating code, refer to:

- `godot-gdextension-cpp-examples/src/` - Official examples
- `godot-cpp/include/godot_cpp/classes/` - Available Godot classes
- `godot-cpp/test/src/` - Test examples with various patterns
- Project-specific documentation in `doc/` directory (if exists)

## Documentation Standards

- **Diagrams**: Use Mermaid format (flowcharts, state diagrams, sequence diagrams, class diagrams, architecture diagrams). Do NOT use ASCII art or plain text diagrams.
- **Documentation files**: Create both English (primary) and Chinese (`.zh-cn` suffix) versions; use the same Mermaid syntax in both.

## Additional Guidelines

- Do NOT write GDScript unless explicitly requested for comparison
- Always verify build commands use Docker-based scripts
- Check Godot 4.5 API documentation for available classes and methods
- Follow Google C++ Style Guide for code formatting
- Use tabs for indentation (displayed as 4 spaces)
- Project-specific names (e.g. `GODOT_PROJECT_NAME` in `SConstruct`, library names, `.gdextension` paths) vary per project - check project configuration files
