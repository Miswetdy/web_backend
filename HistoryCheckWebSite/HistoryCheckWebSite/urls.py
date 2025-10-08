# urls.py
from django.urls import path
from django.contrib import admin
from historycheck import views

urlpatterns = [
    path("admin/", admin.site.urls),

    path('persons/', views.HistoryPersonList.as_view(), name='persons-list'),                     # GET список + фильтрация, POST создать
    path('persons/<int:pk>/', views.HistoryPersonDetail.as_view(), name='person-detail'),         # GET одна, PUT обновление, DELETE удаление
    path('persons/<int:pk>/add_to_order/', views.AddToHistoryCheckOrder.as_view(), name='person-add-to-order'),  # POST добавление в заявку-черновик
    path('persons/<int:pk>/upload_image/', views.UploadHistoryPersonImage.as_view(), name='person-upload-image'), # POST добавить/заменить изображение
    path('orders/basket_icon/', views.HistoryCheckOrderBasketIcon.as_view(), name='order-basket-icon'),       # GET корзина
    path('orders/', views.HistoryCheckOrderList.as_view(), name='orders-list'),                        # GET список заявок
    path('orders/<int:pk>/', views.HistoryCheckOrderDetailView.as_view(), name='order-detail'),               # GET одна заявка
    path('orders/<int:pk>/update/', views.HistoryCheckOrderUpdate.as_view(), name='order-update'),            # PUT изменить поля заявки
    path('orders/<int:pk>/form/', views.HistoryCheckOrderForm.as_view(), name='order-form'),                  # PUT сформировать создателем
    path('orders/<int:pk>/complete/', views.HistoryCheckOrderComplete.as_view(), name='order-complete'),      # PUT завершить/отклонить модератором
    path('orders/<int:pk>/delete/', views.HistoryCheckOrderDelete.as_view(), name='order-delete'),            # DELETE удалить
    path('order_items/<int:pk>/update/', views.HistoryCheckOrderItemUpdate.as_view(), name='order-item-update'), # PUT изменить item
    path('order_items/<int:pk>/delete/', views.HistoryCheckOrderItemDelete.as_view(), name='order-item-delete'), # DELETE удалить item
    path('users/register/', views.UserForHistoryCheckRegister.as_view(), name='user-register'),   # POST регистрация
    path('users/login/', views.UserForHistoryCheckLogin.as_view(), name='user-me'),                 # POST аутентификация
    path('users/me/', views.UserForHistoryCheckDetail.as_view(), name='user-login'),            # GET/PUT профиль
    path('users/logout/', views.UserForHistoryCheckLogout.as_view(), name='user-logout'),         # POST деавторизация
]
