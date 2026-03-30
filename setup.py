from setuptools import find_packages, setup

setup(
    name="email-summarizer",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi==0.115.0",
        "uvicorn[standard]==0.32.0",
        "pydantic==2.9.2",
        # Add other from requirements.txt
    ],
    extras_require={
        "dev": ["pytest", "ruff", "black", "mypy"],
        "ollama": ["ollama==0.3.3"],
        "groq": ["groq==0.4.1"],
    },
)
