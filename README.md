# DCAT-AP Hub

`dcat-ap-hub` is a Python library for working with datasets and pretrained models described using DCAT-AP metadata.
It is built around a practical workflow that resolves metadata, downloads artifacts, and loads datasets or models through a single interface.
Currently, metadata parsing supports **JSON-LD** from direct URLs, content negotiation, and local files.

### Typical Workflow

1. Retrieve dataset metadata in DCAT-AP from:
   - remote JSON-LD URLs (`Dataset.from_url(...)`)
   - local metadata files (`Dataset.from_file(...)`)
   - local directories that contain metadata files (`Dataset.from_directory(...)`)

2. Download files referenced by distributions and related resources (`dcat:downloadURL`) into a local dataset directory.

3. Load files or models for use in code:
   - Load files as a lazy `FileCollection` with built-in loaders for common formats such as CSV, Excel, JSON, Parquet, images, PDF, text, HTML/XML, and NumPy arrays.
   - Load pretrained models through Hugging Face, ONNX, or sklearn-style model scripts.

### Benchmarking With Catalogues

Optionally, related resources can be used to attach a processor script that is detected automatically and applied to transform raw files.
This enables the definition of multi-dataset benchmarks as DCAT-AP catalogues, since benchmarking requires each dataset to provide a fixed train-test split, which can be generated through these processor scripts.

### Requirements for Metadata

- Each dataset metadata record must include a `dcat:Dataset` entry.
- Entries with `@type` set to `mls:Model` are treated as models.
- Roles for distributions (`dcat:Distribution`) and related resources (`rdfs:Resource`) can be defined through `dct:conformsTo` and/or `dct:format`, allowing the specification of model types or processors.
- The `dcat:downloadURL` field identifies the files to be downloaded.

### How To Install

```bash
# Base install (datasets, processing)
pip install dcat-ap-hub

# Install with ONNX model loading support
pip install "dcat-ap-hub[onnx]"

# Install with Hugging Face model loading support
pip install "dcat-ap-hub[huggingface]"

# Install with S3-compatible download support (MinIO, R2, Wasabi, AWS S3, ...)
pip install "dcat-ap-hub[s3]"
```

### Example of Loading a Dataset

```python
from dcat_ap_hub import Dataset

url = "https://ki-daten.hlrs.de/de/dataset/https-piveau-io-set-data-predictive-maintenance-ttl"

ds = Dataset.from_url(url)
files = ds.download(data_dir="./data")
```

### Example of Loading a Huggingface Model

```python
from dcat_ap_hub import Dataset

url = "https://ki-daten.hlrs.de/de/model/prajjwal1-bert-tiny"

ds = Dataset.from_url(url)
files = ds.download(data_dir="./data")
model, processor, metadata = ds.load_model(model_dir="./models")
```

### Example of Loading a SKLearn Model

```python
from dcat_ap_hub import Dataset

url = "https://ki-daten.hlrs.de/de/model/https-piveau-io-set-data-pre-trained-transformer"

ds = Dataset.from_url(url)
files = ds.download(data_dir="./data")
model = ds.load_model(model_dir="./models")
```

### Example of Processing a Dataset if Available

```python
from dcat_ap_hub import Dataset

url = "https://ki-daten.hlrs.de/de/dataset/https-piveau-io-set-data-predictive-maintenance-ttl"

ds = Dataset.from_url(url)
files = ds.download(data_dir="./data")
processed = ds.process(processed_dir="./processed")
```

### S3-Compatible Downloads

For `s3://` download URLs, the service endpoint is read from `dcat:accessURL` in the metadata record:

```json
{
  "@type": "dcat:Distribution",
  "dcat:accessURL": "https://minio.example.org",
  "dcat:downloadURL": "s3://my-bucket/datasets/pmd/data.csv"
}
```

Authentication uses boto3's standard credential chain (environment variables, `~/.aws/credentials`, or IAM role).

### Funding

This project was developed using resources from the HammerHAI project, an EU co-funded AI Factory initiative operated by the High-Performance Computing Center Stuttgart and supported by the European Commission as well as German federal and state ministries. It is funded by the European High Performance Computing Joint Undertaking under Grant Agreement No. 101234027.
