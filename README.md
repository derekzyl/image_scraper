# Receipt Extractor

Turn PalmPay receipt screenshots into a CSV.

Each row contains:

- Receipt number (the transaction ID)
- Name (the recipient)
- Sender name
- Recipient number (the account after the bank name, with a `0` added in front)
- Source file

`7077177416` becomes `07077177416`. `812 689 3701` becomes `08126893701`. An account that already starts with `0` is kept as it is.

You can upload many images at once, drop more in later, edit any cell, then either create a new CSV or add the rows to a CSV you already have.

## Click to open

On this Linux computer, double-click **Receipt Extractor** on the Desktop, or `Receipt Extractor.desktop` in this folder. That opens the app with no terminal.

The program itself is the `dist/ReceiptExtractor` folder (about 400 MB, because the text reader is included). Give someone that whole folder. They double-click `ReceiptExtractor` inside it. Python does not need to be installed.

To build it again:

```bash
./build_executable.sh
```

On Windows, run `build_executable.bat` on a Windows PC. It creates `dist\ReceiptExtractor\ReceiptExtractor.exe`. A Windows `.exe` has to be built on Windows.

## Run from source

You do not need to install Python or uv yourself. The first launch downloads them if they are missing, then installs the app libraries. That step needs an internet connection and can take a few minutes. Later launches work offline.

**Windows:** double-click `run.bat`

**Linux or Mac:**

```bash
chmod +x run.sh
./run.sh
```
# image_scraper
