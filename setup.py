import os

from setuptools import setup

setup(
    name="ktml-check",
    author="Cory Todd",
    author_email="cory.todd@canonical.com",
    description="",
    url="https://github.com/corytodd/ktml-check",
    license="GPLv2",
    long_description=open(
        os.path.join(os.path.dirname(__file__), "README.md"), "r"
    ).read(),
    long_description_content_type="text/markdown",
    packages=["ml_check"],
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "ktml-check = ml_check.run:main",
        ]
    },
    classifiers=[
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Operating System :: POSIX :: Linux",
    ],
    install_requires=[
        "networkx",
        "requests",
        "unidiff",
        "pre-commit",
        "isort",
        "black",
        "networkx",
        "requests",
        "unidiff",
        "pytest",
        "pytest-cov",
        "python-dateutil",
        "launchpadlib",
    ],
    zip_safe=False,
)
