from setuptools import setup, find_packages

setup(
    name="nullstate-cli",
    version="0.1.0",
    description="NullState CLI — Terminal interface for the autonomous payment layer",
    packages=find_packages(),
    install_requires=[
        "requests>=2.28",
        "cryptography>=41.0",
        "rich>=13.0",
    ],
    entry_points={
        "console_scripts": [
            "nullstate=nullstate_cli.cli:main",
        ],
    },
    python_requires=">=3.10",
)
