from setuptools import find_namespace_packages, setup

from ml_check import __version__ as VERSION

setup(
    version=VERSION,
    packages=find_namespace_packages(include=["ml_check"]),
    include_package_data=True,
    exclude_package_data={"": ["snap/*", "tests/*"]},
)
