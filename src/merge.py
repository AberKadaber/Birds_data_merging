import pandas as pd
from datetime import datetime

# Названия столбцов (заполните нужными значениями)
ring_column = 'Ring'  # столбец с номером кольца
date_column = 'Date'  # столбец с датой
additional_column = 'Time'  # дополнительный столбец для сортировки

# Чтение CSV файлов
first_df = pd.read_csv("first.csv", delimiter=';', encoding="windows-1251")
second_df = pd.read_csv("second.csv", delimiter=';', encoding="windows-1251")

first_df.dropna(how='all', inplace=True)
second_df.dropna(how='all', inplace=True)


def parse_time(time_str):
    try:
        return datetime.strptime(time_str, "%d.%m.%y")
    except Exception:
        try:
            return datetime.strptime(time_str, "%d.%m.%Y")
        except Exception as e:
            return pd.NaT


# Преобразуем даты в datetime объекты
first_df['parsed_date'] = first_df[date_column].apply(parse_time)
second_df['parsed_date'] = second_df[date_column].apply(parse_time)

# Сортируем данные
first_df = first_df.sort_values([ring_column, 'parsed_date', additional_column])
second_df = second_df.sort_values([ring_column, 'parsed_date', additional_column])

# Удаляем временную колонку
first_df = first_df.drop('parsed_date', axis=1)
second_df = second_df.drop('parsed_date', axis=1)

# Обработка данных
output_data = []
cnt = 0
last_ring = ""

for _, row in second_df.iterrows():
    current_ring = row[ring_column]

    if last_ring != current_ring:
        cnt += 1
        last_ring = current_ring

        # Ищем соответствующую запись в first_df
        matching_first = first_df[first_df[ring_column] == current_ring]

        if not matching_first.empty:
            first_row = matching_first.iloc[0]
            output_row = [cnt] + first_row.tolist()
            output_data.append(output_row)

        # Добавляем текущую строку из second_df
        output_row = [cnt] + row.tolist()
        output_data.append(output_row)

        if matching_first.empty:
            print(f"Не найдена запись для кольца: {current_ring}")

    else:
        output_row = [cnt] + row.tolist()
        output_data.append(output_row)

columns = ['id'] + first_df.columns.tolist()
output_df = pd.DataFrame(output_data, columns=columns)

output_df.to_csv("out.csv", sep=';', index=False, encoding="windows-1251")
