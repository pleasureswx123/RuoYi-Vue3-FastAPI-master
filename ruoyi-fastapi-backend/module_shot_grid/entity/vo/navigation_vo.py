from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ShotGridNavigationItemModel(BaseModel):
    """Shot Grid 独立业务端导航项。"""

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    route_key: str = Field(description='稳定路由键')
    title: str = Field(description='菜单标题')
    path: str = Field(description='业务端路由地址')
    icon: str | None = Field(default=None, description='菜单图标')
    order_num: int = Field(description='显示顺序')
