import csv
with open('temp_datasets/72a15541-1adf-4349-b00e-7c55c8bc2d81_dataset.csv', 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)
    print("Header:", header)
    for i in range(5):
        try:
            print(f"Row {i}: {next(reader)}")
        except StopIteration:
            break
