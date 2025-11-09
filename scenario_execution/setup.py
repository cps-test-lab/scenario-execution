from setuptools import setup
from glob import glob
import os

package_name = 'scenario_execution'

# Read the long description from README if available
this_directory = os.path.abspath(os.path.dirname(__file__))
try:
    with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()
        long_description_content_type = 'text/markdown'
except FileNotFoundError:
    long_description = 'Scenario Execution for Robotics'
    long_description_content_type = 'text/plain'

setup(
    name=package_name,
    version='1.3.0',
    packages=[
        package_name,
        package_name + '.actions',
        package_name + '.lib_osc',
        package_name + '.osc2_parsing',
        package_name + '.model',
        package_name + '.utils',
        package_name + '.external_methods',
    ],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=[
        'setuptools',
        'antlr4-python3-runtime==4.9.2',
        'pyyaml==6.0.1',
        'py-trees==2.3.0',
    ],
    zip_safe=True,
    maintainer='Frederik Pasch',
    maintainer_email='fred-labs@mailbox.org',
    description='Scenario Execution for Robotics',
    long_description=long_description,
    long_description_content_type=long_description_content_type,
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'scenario_execution = scenario_execution.scenario_execution_base:main',
        ],
        'scenario_execution.actions': [
            'compare = scenario_execution.actions.compare:Compare',
            'increment = scenario_execution.actions.increment:Increment',
            'decrement = scenario_execution.actions.decrement:Decrement',
            'log = scenario_execution.actions.log:Log',
            'run_process = scenario_execution.actions.run_process:RunProcess',
        ],
        'scenario_execution.osc_libraries': [
            'helpers = scenario_execution.get_osc_library:get_helpers_library',
            'standard = scenario_execution.get_osc_library:get_standard_library',
            'types = scenario_execution.get_osc_library:get_types_library',
            'robotics = scenario_execution.get_osc_library:get_robotics_library',
        ],
    },
    package_data={
        package_name: ['lib_osc/*.osc'],
    },
    include_package_data=True,
)
