# Testing Documentation

Testing guides, checklists, and test results.

## 🧪 Contents

### Testing Guides

#### [UI_TESTING_CHECKLIST.md](UI_TESTING_CHECKLIST.md)
Comprehensive UI testing checklist:
- Page load and rendering tests
- Navigation testing
- Interactive element testing
- Responsive design testing
- Accessibility testing
- Cross-browser compatibility

### Test Results

#### [TEST_RESULTS_2025-11-13.md](TEST_RESULTS_2025-11-13.md)
Test results from November 13, 2025:
- Story API testing
- UI functionality testing
- Integration testing
- Performance testing

#### [STORY_API_TESTING_SUMMARY.md](STORY_API_TESTING_SUMMARY.md)
Story API endpoint testing summary:
- `/api/stories` - List stories
- `/api/stories/{id}` - Get story details
- `/api/stories/generate` - Generate stories
- Response validation
- Error handling

---

## 🔬 Testing Strategy

### Unit Tests
- Python tests with `pytest`
- Located in `tests/` directory
- Run: `pytest`

### Integration Tests
- API endpoint testing
- Database interaction testing
- Story generation pipeline testing

### UI Tests
- Manual testing with checklist
- Visual regression testing
- Accessibility testing

### Performance Tests
- Load testing
- Response time measurement
- Resource usage monitoring

---

## 🚀 Running Tests

### Run All Tests
```bash
pytest
```

### Run with Coverage
```bash
pytest --cov=app --cov-report=html
```

### Run Specific Tests
```bash
pytest tests/test_story_crud.py
pytest tests/test_models.py -v
```

### Run Linters
```bash
# Code formatting
black --check app/

# Import sorting
isort --check-only app/

# Type checking
mypy app/ --ignore-missing-imports
```

---

## 📋 Test Coverage

### Current Coverage
- Story CRUD operations: ✅ 100%
- Story generation: ✅ 95%
- API endpoints: ✅ 90%
- Models/Validation: ✅ 100%

### Coverage Goals
- Maintain >90% overall coverage
- 100% for critical paths
- Integration test coverage for all APIs

---

## 📚 Further Reading

- **Development**: See [../development/DEVELOPMENT.md](../development/DEVELOPMENT.md)
- **CI/CD**: See [../development/CI-CD.md](../development/CI-CD.md)
- **Planning**: See [../planning/](../planning/)
