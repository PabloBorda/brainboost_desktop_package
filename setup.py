from setuptools import setup, find_packages

setup(
    name="brainboost_desktop_package",
    version="0.1.0",
    description="A package for desktop monitoring, screenshot capture, and OCR processing.",
    author="Pablo Tomas Borda",
    author_email="pablotomasborda@gmail.com",
    packages=find_packages(),
    include_package_data=True,  # Ensure package data is included
    install_requires=[
        "opencv-python-headless==4.10.0.84",
        "numpy>=1.24.0,<2.0.0",
        "PyAutoGUI==0.9.54",
        "pytesseract==0.3.13",
        "mss==9.0.2",
        "Pillow==11.0.0",
        "screeninfo==0.8.1",
        "pynput==1.7.7",
        "PyGetWindow==0.0.9",
    ],
    extras_require={
        "dev": [
            "pytest==8.3.4",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.9',  # Update to 3.9 since 'files' is used
    package_data={
        "brainboost_ocr_package": ["resources/frozen_east_text_detection.pb"],
    },
)
