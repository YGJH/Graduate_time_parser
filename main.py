from controller import lab_census_system


def run(input_fn=input, system_factory=lab_census_system.LabCensusSystem):
    school = input_fn('欲查詢學校[1.交大 2.中央 3.清大 4.陽明]，輸入數字：')
    name = input_fn('教授名稱：')
    sample_count = int(input_fn('參考最近碩士畢業生的數量：'))
    filter_cnt = input_fn('欲過濾的系所數量（選填）：')

    system = system_factory(school, name, sample_count, filter_cnt)
    try:
        system.Search()
    except lab_census_system.NycuBrowserUnavailableError as error:
        print(error)
        return
    result = system.Show()
    print(f"最近 {sample_count} 筆碩士畢業生紀錄中")
    print(f"{result[0]}\t位第一年畢業")
    print(f"{result[1]}\t位第二年畢業")
    print(f"{result[2]}\t位第三年畢業")
    print(f"{result[3]}\t位第四年畢業")
    print(f"{result[4]}\t位第五年以上畢業")


if __name__ == "__main__":
    run()
