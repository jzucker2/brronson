# Agent Guidelines for Brronson Project

This document outlines the requirements and guidelines for AI agents working on the Brronson project. It ensures code quality, consistency, and maintainability.

## Pre-commit Hooks

All code changes **MUST** pass pre-commit hooks before being committed. The project uses the following pre-commit hooks:

### Required Hooks

1. **trailing-whitespace** - Removes trailing whitespace from files
2. **end-of-file-fixer** - Ensures files end with a newline
3. **check-yaml** - Validates YAML file syntax
4. **check-added-large-files** - Prevents committing large files (>500KB)
5. **black** - Formats Python code (line length: 79 characters)
6. **flake8** - Lints Python code for style and errors

### Pre-commit Configuration

The pre-commit hooks are configured in `.pre-commit-config.yaml`. The configuration includes:

- **Black**: Python code formatter with 79 character line length
- **Flake8**: Python linter for PEP 8 compliance
- **Standard hooks**: Basic file checks and formatting

### Running Pre-commit Hooks

Agents should ensure pre-commit hooks are installed and run before committing:

```bash
# Install pre-commit hooks (first time only)
pre-commit install

# Run pre-commit hooks manually on all files
pre-commit run --all-files

# Run pre-commit hooks on staged files (automatic on commit)
pre-commit run
```

### Pre-commit Hook Requirements

**Agents MUST:**
1. Ensure all code passes pre-commit hooks before committing
2. Fix any issues reported by pre-commit hooks
3. Run `pre-commit run --all-files` before finalizing changes
4. Never skip pre-commit hooks unless explicitly requested by the user

## Linting Requirements

### Code Style

The project follows **PEP 8** Python style guidelines with the following specifications:

- **Line Length**: 79 characters (enforced by Black)
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Prefer double quotes for strings, single quotes for characters
- **Imports**: Organized in the following order:
  1. Standard library imports
  2. Third-party imports
  3. Local application imports

### Black Formatting

All Python code **MUST** be formatted with Black:

```bash
# Format all Python files
black .

# Format specific file
black app/main.py

# Check formatting without making changes
black --check .
```

**Black Configuration:**
- Line length: 79 characters
- Target Python version: 3.11+

### Flake8 Linting

All Python code **MUST** pass Flake8 linting:

```bash
# Lint all Python files
flake8 .

# Lint specific file
flake8 app/main.py
```

**Flake8 Checks:**
- PEP 8 style violations
- Syntax errors
- Undefined names
- Unused imports
- Complex code warnings

### Linting Rules

**Agents MUST:**
1. Run `black` to format code before committing
2. Run `flake8` to check for linting errors
3. Fix all linting errors before committing
4. Ensure code follows PEP 8 guidelines
5. Use meaningful variable and function names
6. Add docstrings to all functions and classes
7. Keep functions focused and single-purpose
8. Avoid overly complex code (use helper functions)

## Code Quality Standards

### Documentation

- **Docstrings**: All functions and classes must have docstrings
- **Type Hints**: Use type hints for function parameters and return values
- **Comments**: Add comments for complex logic or non-obvious code
- **README**: Update README.md when adding new features or endpoints

### Testing

- **Test Coverage**: All new features must have corresponding tests
- **Test Naming**: Use descriptive test names (e.g., `test_recover_subtitle_folders_dry_run`)
- **Test Organization**: Group related tests in test classes
- **Test Data**: Use temporary directories for file system tests
- **Test Cleanup**: Always clean up test data in `tearDown` methods

### Error Handling

- **HTTP Exceptions**: Use FastAPI's `HTTPException` for API errors
- **Error Messages**: Provide clear, descriptive error messages
- **Error Logging**: Log errors with appropriate log levels
- **Error Metrics**: Record errors in Prometheus metrics

### Security

- **Directory Validation**: Always validate directory paths before operations
- **System Protection**: Prevent operations on critical system directories
- **Path Resolution**: Use `Path.resolve()` to prevent path traversal attacks
- **Input Validation**: Validate all user inputs

## Project Structure

### File Organization

```
brronson/
├── app/
│   ├── __init__.py
│   ├── main.py          # Main application code
│   └── version.py       # Version information
├── tests/
│   ├── __init__.py
│   └── test_main.py     # Test suite
├── .pre-commit-config.yaml  # Pre-commit hooks configuration
├── requirements.txt     # Production dependencies
├── requirements-dev.txt # Development dependencies
└── README.md           # Project documentation
```

### Code Organization

- **Routes**: Define all API routes in `app/main.py`
- **Helper Functions**: Place reusable functions before route definitions
- **Constants**: Define constants at the module level
- **Metrics**: Define Prometheus metrics after constants, before routes

## Agent Workflow

### Before Making Changes

1. **Read the Codebase**: Understand existing patterns and conventions
2. **Check Requirements**: Review this document and project requirements
3. **Plan Changes**: Outline the changes before implementing

### During Development

1. **Follow Patterns**: Match existing code style and patterns
2. **Write Tests**: Create tests alongside implementation
3. **Run Linters**: Frequently run Black and Flake8
4. **Check Tests**: Run tests to ensure nothing breaks

### Before Committing

1. **Format Code**: Run `black .` to format all code
2. **Lint Code**: Run `flake8 .` to check for errors
3. **Run Tests**: Execute `pytest` to verify all tests pass
4. **Run Pre-commit**: Execute `pre-commit run --all-files`
5. **Update Docs**: Update README.md if adding new features
6. **Review Changes**: Review all changes before committing

## Common Issues and Solutions

### Black Formatting Issues

**Problem**: Code doesn't match Black's formatting
**Solution**: Run `black .` to auto-format code

### Flake8 Line Length Issues

**Problem**: Lines exceed 79 characters
**Solution**: Break long lines or use Black to auto-format

### Import Order Issues

**Problem**: Imports not in correct order
**Solution**: Organize imports: stdlib → third-party → local

### Missing Docstrings

**Problem**: Functions missing docstrings
**Solution**: Add docstrings following Google or NumPy style

### Test Failures

**Problem**: Tests fail after changes
**Solution**:
1. Review test output for specific failures
2. Ensure test data is properly set up
3. Check that environment variables are correctly set in tests

## Environment Variables

When writing tests or code that uses environment variables:

1. **Save Original Values**: Store original values in `setUp`
2. **Restore Values**: Restore original values in `tearDown`
3. **Use Temporary Directories**: Use `tempfile.mkdtemp()` for test directories
4. **Clean Up**: Always clean up temporary directories

## Prometheus Metrics

When adding new features:

1. **Define Metrics**: Add metric definitions after constants
2. **Record Metrics**: Record metrics at appropriate points in code
3. **Use Labels**: Use meaningful labels for metrics
4. **Document Metrics**: Update README.md with new metrics
5. **Test Metrics**: Add tests to verify metrics are recorded

## API Endpoint Guidelines

When adding new API endpoints:

1. **Follow Naming**: Use RESTful naming conventions
2. **Add Documentation**: Include comprehensive docstrings
3. **Add Tests**: Create comprehensive test coverage
4. **Add Metrics**: Record Prometheus metrics
5. **Update README**: Document the endpoint in README.md
6. **Error Handling**: Implement proper error handling
7. **Validation**: Validate all inputs

## Checklist for Agents

Before submitting code, ensure:

- [ ] All code is formatted with Black
- [ ] All code passes Flake8 linting
- [ ] All pre-commit hooks pass
- [ ] All tests pass
- [ ] New features have tests
- [ ] Documentation is updated (README.md)
- [ ] Prometheus metrics are added (if applicable)
- [ ] Error handling is implemented
- [ ] Code follows project patterns
- [ ] No hardcoded paths or values
- [ ] Environment variables are used for configuration
- [ ] Security checks are in place

## Additional Resources

- **Black Documentation**: https://black.readthedocs.io/
- **Flake8 Documentation**: https://flake8.pycqa.org/
- **Pre-commit Documentation**: https://pre-commit.com/
- **PEP 8 Style Guide**: https://pep8.org/
- **FastAPI Documentation**: https://fastapi.tiangolo.com/

## Summary

Agents working on this project must:
1. **Always** run pre-commit hooks before committing
2. **Always** format code with Black
3. **Always** lint code with Flake8
4. **Always** write tests for new features
5. **Always** update documentation
6. **Always** follow project patterns and conventions
7. **Never** skip pre-commit hooks
8. **Never** commit code that doesn't pass linting
9. **Never** commit code without tests
10. **Never** hardcode paths or configuration values

By following these guidelines, agents ensure code quality, maintainability, and consistency across the project.
