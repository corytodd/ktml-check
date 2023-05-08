from setuptools import find_namespace_packages, setup

setup(
    packages=find_namespace_packages(include=["ml_check"]),
    include_package_data=True,
    exclude_package_data={"": ["snap/*", "tests/*"]},
)
