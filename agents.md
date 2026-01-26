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
make pre-commit-install
# Or: pre-commit install

# Run pre-commit hooks manually on all files
make pre-commit-run
# Or: pre-commit run --all-files

# Run pre-commit hooks on staged files (automatic on commit)
pre-commit run
```

### Pre-commit Hook Requirements

**Agents MUST:**
1. Run `make check` before running pre-commit hooks
2. Ensure all code passes pre-commit hooks before committing
3. Fix any issues reported by pre-commit hooks
4. Run `make pre-commit-run` or `pre-commit run --all-files` before finalizing changes
5. Never skip pre-commit hooks unless explicitly requested by the user

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
# Format all Python files (recommended: use make)
make format

# Or format directly with black
black app/ tests/ --line-length=79

# Format specific file
black app/main.py

# Check formatting without making changes
black --check app/ tests/
```

**Black Configuration:**
- Line length: 79 characters
- Target Python version: 3.11+

### Flake8 Linting

All Python code **MUST** pass Flake8 linting:

```bash
# Lint all Python files (checks only, doesn't fix)
make lint

# Auto-fix linting issues where possible
make lint-fix

# Or lint directly with flake8
flake8 app/ tests/

# Lint specific file
flake8 app/main.py
```

**Flake8 Checks:**
- PEP 8 style violations
- Syntax errors
- Undefined names
- Unused imports
- Complex code warnings

### Make Check Command

The project provides a convenient `make check` command that runs both formatting and linting:

```bash
# Run format and lint checks
make check
```

This command:
1. Runs `make format` (formats code with Black)
2. Runs `make lint` (lints code with Flake8 - checks only)

**If `make check` reports linting errors, agents should run `make lint-fix` to auto-fix issues where possible.**

### Make Lint-Fix Command

The `make lint-fix` command attempts to automatically fix linting issues:

```bash
# Auto-fix linting issues
make lint-fix
```

This command:
1. Runs `black` to format code
2. Runs `autopep8` to fix PEP 8 violations automatically

**Agents MUST run `make check` before committing code, and if linting errors remain, run `make lint-fix` to attempt auto-fixes.**

### Linting Rules

**Agents MUST:**
1. Run `make check` to format and lint code before committing
2. Fix all linting errors before committing
3. Ensure code follows PEP 8 guidelines
4. Use meaningful variable and function names
5. Add docstrings to all functions and classes
6. Keep functions focused and single-purpose
7. Avoid overly complex code (use helper functions)

## Code Quality Standards

### Documentation

- **Docstrings**: All functions and classes must have docstrings
- **Type Hints**: Use type hints for function parameters and return values
- **Comments**: Add comments for complex logic or non-obvious code
- **README**: Update README.md when adding new features or endpoints

### Testing

- **Test Coverage**: All new features must have corresponding tests
- **Test New Code**: When adding new code, functions, or endpoints, write tests to verify they work correctly
- **Test New Conditions**: When adding new error conditions, exception handlers, or conditional logic, write tests to verify each condition is handled correctly
- **Test Error Cases**: Test both success and error paths, including edge cases and error conditions
- **Test Cross-Platform**: When adding platform-specific code (e.g., errno handling), test that it works correctly across platforms
- **Test Naming**: Use descriptive test names (e.g., `test_recover_subtitle_folders_dry_run`, `test_salvage_stale_file_handle_error`)
- **Test Organization**: Group related tests in test classes
- **Test Data**: Use temporary directories for file system tests
- **Test Cleanup**: Always clean up test data in `tearDown` methods
- **Running Tests**: Always run `make test` before committing to ensure all tests pass
- **Test Failures**: Never commit code if tests fail - fix the code or tests first

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

## Makefile Commands

The project provides convenient Makefile commands for common tasks:

```bash
# Format and lint code (MUST run before committing)
make check

# Auto-fix linting issues where possible
make lint-fix

# Format code with Black
make format

# Lint code with Flake8 (checks only)
make lint

# Run tests
make test

# Run tests with coverage
make test-coverage

# Install pre-commit hooks
make pre-commit-install

# Run pre-commit hooks on all files
make pre-commit-run

# Run unit tests
make test

# Run tests with coverage
make test-coverage

# Run all CI checks (pre-commit + tests)
make ci-check
```

**Agents MUST use `make check` as part of their workflow before committing.**

## File Size Guidelines

**Agents MUST:**
1. **Split Large Files**: If a file exceeds 500 lines, consider splitting it into multiple files
2. **Modular Design**: Keep files focused on a single responsibility
3. **Reasonable PR Size**: Avoid creating PRs with files larger than 1000 lines
4. **Break Down Changes**: For large features, split into multiple smaller PRs when possible
5. **File Organization**: Use appropriate directory structure (e.g., `routes/` for API endpoints)

**File Organization:**
- Keep individual route files under 500 lines when possible
- Split helper functions into separate modules
- Group related functionality together
- Use subdirectories for logical grouping (e.g., `app/routes/`)

## Agent Workflow

### Before Making Changes

1. **Read the Codebase**: Understand existing patterns and conventions
2. **Check Requirements**: Review this document and project requirements
3. **Plan Changes**: Outline the changes before implementing
4. **Consider File Size**: If adding significant code, plan how to organize it across files

### During Development

1. **Follow Patterns**: Match existing code style and patterns
2. **Write Tests**: Create tests alongside implementation
3. **Run Make Check**: Frequently run `make check` to format and lint code
4. **Run Tests**: Frequently run `make test` to ensure tests pass
5. **Fix Issues**: Address any test failures or linting errors immediately
6. **Monitor File Size**: If a file grows beyond 500 lines, consider splitting it

### Before Committing

1. **Run Make Check**: Execute `make check` to format and lint code (runs `format` and `lint` targets)
2. **Fix Linting Issues**: If linting errors are found, run `make lint-fix` to auto-fix issues where possible
3. **Re-run Make Check**: Run `make check` again to verify all issues are resolved
4. **Run Tests**: Execute `make test` to run unit tests and ensure they pass
5. **Run Pre-commit**: Execute `pre-commit run --all-files` or `make pre-commit-run`
6. **Update README**: **ALWAYS** update README.md when adding new endpoints, routes, or features. Include:
   - Endpoint path and method in the API Endpoints section
   - Full documentation with usage examples, configuration, and response formats
7. **Review Changes**: Review all changes before committing

**Note**: The `make check` command runs both formatting (Black) and linting (Flake8) in sequence. If linting errors remain after formatting, use `make lint-fix` to attempt automatic fixes before manually addressing any remaining issues. **All tests MUST pass before committing.**

## Common Issues and Solutions

### Black Formatting Issues

**Problem**: Code doesn't match Black's formatting
**Solution**: Run `make format` or `black app/ tests/ --line-length=79` to auto-format code

### Flake8 Line Length Issues

**Problem**: Lines exceed 79 characters
**Solution**: Run `make lint-fix` to auto-fix, or manually break long lines

### Import Order Issues

**Problem**: Imports not in correct order
**Solution**: Organize imports: stdlib → third-party → local

### Missing Docstrings

**Problem**: Functions missing docstrings
**Solution**: Add docstrings following Google or NumPy style

### Markdown Linting Issues

**Problem**: Markdown files have linting errors (duplicate headings, missing code block languages, etc.)
**Solution**:
- Fix duplicate headings by making them unique
- Add language identifiers to code blocks (e.g., ` ```python`, ` ```bash`, ` ```text`)
- Run `make check` which includes markdown linting via pre-commit hooks

### Test Failures

**Problem**: Tests fail after changes
**Solution**:
1. Run `make test` to see detailed test output
2. Review test output for specific failures
3. Ensure test data is properly set up
4. Check that environment variables are correctly set in tests
5. Fix the code or tests to make all tests pass before committing

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
6. **Skip Metrics**: For copy/move operations, include metrics for skipped items (e.g., `*_skipped_total`) to track when destinations already exist

## API Endpoint Guidelines

When adding new API endpoints:

1. **Follow Naming**: Use RESTful naming conventions
2. **Add Documentation**: Include comprehensive docstrings
3. **Add Tests**: Create comprehensive test coverage
4. **Add Metrics**: Record Prometheus metrics
5. **Update README**: **ALWAYS** document the endpoint in README.md with:
   - Endpoint path and HTTP method
   - Description of what it does
   - Configuration requirements (environment variables)
   - Usage examples with curl commands
   - Response format examples
   - Feature list
6. **Error Handling**: Implement proper error handling
7. **Validation**: Validate all inputs
8. **Skip Existing**: For copy/move operations, skip existing destination files/folders rather than overwriting (log skipped items in response and metrics)
9. **Batch Size**: For copy/move operations, implement `batch_size` parameter that limits items processed per request. Only count actually copied/moved items toward the limit (not skipped items), making operations re-entrant
10. **Re-entrancy**: Ensure operations can be safely resumed by subsequent requests - skipped items should not count toward batch limits

## Checklist for Agents

Before submitting code, ensure:

- [ ] `make check` passes (formats and lints code)
- [ ] `make lint-fix` has been run if linting errors were found
- [ ] All code is formatted with Black
- [ ] All code passes Flake8 linting
- [ ] Markdown files pass linting (no duplicate headings, code blocks have languages)
- [ ] `make test` passes (all unit tests must pass)
- [ ] All pre-commit hooks pass (`make pre-commit-run`)
- [ ] New features have tests
- [ ] **README.md is updated with new endpoint documentation** (endpoint path, usage examples, configuration, response format)
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
1. **Always** run `make check` before committing (formats and lints code)
2. **Always** run `make lint-fix` if linting errors are found after `make check`
3. **Always** run `make test` before committing (all unit tests must pass)
4. **Always** run pre-commit hooks before committing (`make pre-commit-run`)
5. **Always** format code with Black (via `make format` or `make check`)
6. **Always** lint code with Flake8 (via `make lint` or `make check`)
7. **Always** write tests for new features
8. **Always** update README.md when adding new endpoints or routes (include endpoint path, usage examples, configuration, response format)
9. **Always** follow project patterns and conventions
10. **Always** keep files under 500 lines when possible, split larger files
11. **Never** skip pre-commit hooks
12. **Never** commit code that doesn't pass `make check`
13. **Never** commit code that doesn't pass linting
14. **Never** commit code if tests fail (`make test` must pass)
15. **Never** commit code without tests
16. **Never** commit code without updating README.md for new endpoints
17. **Never** hardcode paths or configuration values
18. **Never** create files larger than 1000 lines in a single PR

By following these guidelines, agents ensure code quality, maintainability, and consistency across the project.
