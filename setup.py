import os
import sys

from setuptools import setup

from ml_check.run import VERSION

if sys.version_info < (3, 8):
    print("ml-check requires Python 3.8 or higher")
    sys.exit(1)

setup(
    name="ml-check",
    version=VERSION,
    author="Cory Todd",
    author_email="cory.todd@canonical.com",
    description="",
    url="https://github.com/corytodd/ml-check",
    license="GPLv2",
    long_description=open(
        os.path.join(os.path.dirname(__file__), "README.md"), "r"
    ).read(),
    long_description_content_type="text/markdown",
    packages=["ml_check"],
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "ml-check = ml_check.run:main",
        ]
    },
    classifiers=[
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Operating System :: POSIX :: Linux",
    ],
    install_requires=["networkx", "requests", "unidiff"],
    zip_safe=False,
)
