from setuptools import find_packages, setup

setup(
    name='sidestacker',
    version='1.0.0',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    instal_requires=[
        'flask'
    ]
)
