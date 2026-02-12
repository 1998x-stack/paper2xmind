"""
Pytest configuration file
"""
import pytest
import sys
import os

# Add the project root to the path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment"""
    # Create temporary directories if needed
    import tempfile
    import os
    
    # Store original values to restore after test
    original_data_dir = os.environ.get('DATA_DIR')
    original_output_dir = os.environ.get('OUTPUT_DIR')
    
    # Set up temporary directories for testing
    temp_data = tempfile.mkdtemp(prefix='test_data_')
    temp_output = tempfile.mkdtemp(prefix='test_output_')
    
    os.environ['DATA_DIR'] = temp_data
    os.environ['OUTPUT_DIR'] = temp_output
    
    yield  # This is where the test runs
    
    # Cleanup after test
    import shutil
    if os.path.exists(temp_data):
        shutil.rmtree(temp_data)
    if os.path.exists(temp_output):
        shutil.rmtree(temp_output)
    
    # Restore original values
    if original_data_dir:
        os.environ['DATA_DIR'] = original_data_dir
    else:
        os.environ.pop('DATA_DIR', None)
        
    if original_output_dir:
        os.environ['OUTPUT_DIR'] = original_output_dir
    else:
        os.environ.pop('OUTPUT_DIR', None)


@pytest.fixture
def sample_pdf_path():
    """Provide a sample PDF path for testing"""
    # In a real scenario, we might create a temporary PDF
    # For now, we'll return a placeholder
    import tempfile
    import os
    
    # Create a temporary PDF file for testing
    temp_pdf = os.path.join(tempfile.gettempdir(), 'test_paper.pdf')
    
    # Create a minimal PDF content (not a real PDF, just for testing file existence)
    with open(temp_pdf, 'wb') as f:
        f.write(b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n')
    
    yield temp_pdf
    
    # Cleanup
    if os.path.exists(temp_pdf):
        os.remove(temp_pdf)


# Enable asyncio support for pytest
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark async tests"""
    for item in items:
        if 'asyncio' in item.keywords:
            item.add_marker(pytest.mark.asyncio)