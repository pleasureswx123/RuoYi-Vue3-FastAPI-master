def format_shot_code(shot_no: int) -> str:
    """场内镜序转为至少四位的数字镜头号，不截断较大的编号。"""
    return f'{shot_no:04d}'
