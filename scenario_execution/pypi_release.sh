#!/bin/bash
# PyPI Release Script for scenario_execution package
# This script helps with building and uploading the package to PyPI

set -e  # Exit on error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PACKAGE_DIR="$SCRIPT_DIR"
VENV_DIR="$PACKAGE_DIR/.pypi_venv"

echo "=========================================="
echo "scenario_execution PyPI Release Helper"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "$PACKAGE_DIR/setup.py" ]; then
    echo "Error: setup.py not found. Make sure you're in the package directory."
    exit 1
fi

# Setup virtual environment with latest tools
setup_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        echo "Creating virtual environment for PyPI tools..."
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        pip install --upgrade pip
        pip install --upgrade build twine
        echo "✓ Virtual environment created and tools installed"
    else
        echo "Using existing virtual environment"
        source "$VENV_DIR/bin/activate"
    fi
}

# Activate venv on startup
setup_venv

# Function to display menu
show_menu() {
    echo ""
    echo "Select an action:"
    echo "1) Clean build artifacts"
    echo "2) Build package"
    echo "3) Check package"
    echo "4) Upload to TestPyPI"
    echo "5) Upload to PyPI"
    echo "6) Full workflow (clean -> build -> check -> TestPyPI)"
    echo "7) Install locally for testing"
    echo "8) Run tests"
    echo "9) Update PyPI tools (pip, build, twine)"
    echo "0) Exit"
    echo ""
}

# Function to clean build artifacts
clean_build() {
    echo "Cleaning build artifacts..."
    rm -rf "$PACKAGE_DIR/dist/"
    rm -rf "$PACKAGE_DIR/build/"
    rm -rf "$PACKAGE_DIR"/*.egg-info
    echo "✓ Clean complete"
}

# Function to update tools
update_tools() {
    echo "Updating PyPI tools..."
    pip install --upgrade pip build twine
    echo "✓ Tools updated"
    echo ""
    echo "Versions:"
    pip --version
    python3 -m build --version
    python3 -m twine --version
}

# Function to build package
build_package() {
    echo "Building package..."
    cd "$PACKAGE_DIR"
    python3 -m build
    echo "✓ Build complete"
    echo ""
    echo "Built files:"
    ls -lh "$PACKAGE_DIR/dist/"
}

# Function to check package
check_package() {
    echo "Checking package with twine..."
    python3 -m twine check "$PACKAGE_DIR/dist/*"
    echo "✓ Package check complete"
}

# Function to upload to TestPyPI
upload_testpypi() {
    echo "Uploading to TestPyPI..."
    echo "Note: This will modify the version to avoid filename conflicts on TestPyPI"

    # Create a test version with timestamp
    TIMESTAMP=$(date +%Y%m%d%H%M%S)

    # Extract version from setup.py
    if [ -f "$PACKAGE_DIR/setup.py" ]; then
        ORIGINAL_VERSION=$(grep "version=" "$PACKAGE_DIR/setup.py" | head -1 | sed "s/.*version='\([^']*\)'.*/\1/")
        TEST_VERSION="${ORIGINAL_VERSION}.post${TIMESTAMP}"

        echo "Original version: ${ORIGINAL_VERSION}"
        echo "Test version: ${TEST_VERSION}"

        # Backup original setup.py
        cp "$PACKAGE_DIR/setup.py" "$PACKAGE_DIR/setup.py.bak"

        # Modify version in setup.py
        sed -i "s/version='${ORIGINAL_VERSION}'/version='${TEST_VERSION}'/" "$PACKAGE_DIR/setup.py"

        echo "Building with test version: ${TEST_VERSION}"

        # Clean and rebuild
        rm -rf "$PACKAGE_DIR/dist/"
        rm -rf "$PACKAGE_DIR/build/"
        rm -rf "$PACKAGE_DIR"/*.egg-info
        python3 -m build

        # Restore original setup.py
        mv "$PACKAGE_DIR/setup.py.bak" "$PACKAGE_DIR/setup.py"
    else
        echo "Error: setup.py not found"
        return 1
    fi

    echo "You'll need your TestPyPI API token"
    python3 -m twine upload --verbose --repository testpypi "$PACKAGE_DIR/dist/*"
    echo "✓ Upload to TestPyPI complete"
    echo ""
    echo "Install from TestPyPI with:"
    echo "pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ scenario-execution==${TEST_VERSION}"
    echo ""
    echo "Or install latest version from TestPyPI with:"
    echo "pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ scenario-execution"
    echo ""
    echo "Note: --extra-index-url allows pip to fetch dependencies from PyPI"
}

# Function to upload to PyPI
upload_pypi() {
    echo "⚠️  WARNING: You are about to upload to the REAL PyPI!"
    echo "This action cannot be undone for this version."
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Upload cancelled"
        return
    fi
    
    echo "Uploading to PyPI..."
    echo "You'll need your PyPI API token"
    python3 -m twine upload "$PACKAGE_DIR/dist/*"
    echo "✓ Upload to PyPI complete"
    echo ""
    echo "Package available at: https://pypi.org/project/scenario-execution/"
}

# Function to install locally
install_local() {
    echo "Installing package locally..."
    cd "$PACKAGE_DIR"
    pip install -e .
    echo "✓ Local installation complete"
}

# Function to run tests
run_tests() {
    echo "Running tests..."
    cd "$PACKAGE_DIR"

    # Install package with all dependencies in editable mode
    echo "Installing package with dependencies..."
    pip install -e .

    # Install pytest if not already installed
    if ! python3 -c "import pytest" 2>/dev/null; then
        echo "Installing pytest..."
        pip install pytest
    fi

    # Check if test directory exists
    if [ ! -d "test" ] && [ ! -d "tests" ]; then
        echo "No test directory found (looking for 'test' or 'tests')"
        echo "Skipping tests"
        return
    fi

    echo ""
    echo "Running tests..."
    # Run tests from whichever directory exists
    if [ -d "test" ]; then
        python3 -m pytest test/ -v
    elif [ -d "tests" ]; then
        python3 -m pytest tests/ -v
    fi

    echo "✓ Tests complete"
}

# Main loop
while true; do
    show_menu
    read -p "Enter choice [0-9]: " choice
    echo ""
    
    case $choice in
        1)
            clean_build
            ;;
        2)
            build_package
            ;;
        3)
            check_package
            ;;
        4)
            upload_testpypi
            ;;
        5)
            upload_pypi
            ;;
        6)
            clean_build
            echo ""
            build_package
            echo ""
            check_package
            echo ""
            upload_testpypi
            ;;
        7)
            install_local
            ;;
        8)
            run_tests
            ;;
        9)
            update_tools
            ;;
        0)
            echo "Goodbye!"
            deactivate 2>/dev/null || true
            exit 0
            ;;
        *)
            echo "Invalid option. Please try again."
            ;;
    esac
    echo ""
    read -p "Press Enter to continue..."
    echo ""
done
