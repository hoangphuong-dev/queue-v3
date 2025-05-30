# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class CoordinatorController(http.Controller):

    @http.route('/coordinator/patient/<int:patient_id>/data', type='json', auth='user')
    def get_patient_coordinator_data(self, patient_id):
        """Lấy dữ liệu điều phối cho bệnh nhân cụ thể"""
        try:
            patient = request.env['res.partner'].browse(patient_id)

            if not patient.exists() or not patient.is_patient:
                return {'success': False, 'message': 'Bệnh nhân không tồn tại'}

            # Buộc tính toán lại các trường computed
            patient._compute_next_service_recommendations()
            patient._compute_next_priority_services()
            patient._compute_current_active_token()

            # Lấy dữ liệu recommendations
            recommendations = {}
            priority_services = []

            try:
                if patient.next_service_recommendations:
                    recommendations = eval(patient.next_service_recommendations)
                if patient.next_priority_services:
                    priority_services = eval(patient.next_priority_services)
            except Exception as e:
                _logger.error(f"Lỗi khi parse recommendations: {str(e)}")
                recommendations = {}
                priority_services = []

            # Lấy token hiện tại
            current_token = patient.current_active_token_id
            current_service_info = None

            if current_token:
                current_service_info = {
                    'token_id': current_token.id,
                    'token_name': current_token.name,
                    'service_name': current_token.service_id.name,
                    'room_name': current_token.room_id.name if current_token.room_id else 'Chưa phân phòng',
                    'room_code': current_token.room_id.code if current_token.room_id else '',
                    'state': current_token.state,
                    'position': current_token.position,
                    'estimated_wait_time': current_token.estimated_wait_time,
                    'start_time': current_token.start_time,
                    'priority': current_token.priority,
                    'emergency': current_token.emergency
                }

            # Lấy lịch sử token
            token_history = []
            for token in patient.queue_history_ids.sorted('create_date', reverse=True):
                token_history.append({
                    'id': token.id,
                    'name': token.name,
                    'service_name': token.service_id.name,
                    'room_name': token.room_id.name if token.room_id else 'Chưa phân phòng',
                    'state': token.state,
                    'create_date': fields.Datetime.to_string(token.create_date),
                    'start_time': fields.Datetime.to_string(token.start_time) if token.start_time else None,
                    'end_time': fields.Datetime.to_string(token.end_time) if token.end_time else None,
                    'emergency': token.emergency
                })

            # Chuẩn bị dữ liệu recommendations cho JavaScript
            next_services = recommendations if isinstance(recommendations, list) else []

            return {
                'success': True,
                'patient_info': {
                    'id': patient.id,
                    'name': patient.name,
                    'patient_id_number': patient.patient_id_number,
                    'patient_category': patient.patient_category,
                    'age': patient.age,
                    'gender': patient.gender,
                    'queue_package': patient.queue_package_id.name if patient.queue_package_id else None,
                    'current_service_group': patient.current_service_group_id.name if patient.current_service_group_id else None
                },
                'current_service': current_service_info,
                'recommendations': {
                    'next_services': next_services
                },
                'priority_services': priority_services,
                'token_history': token_history,
                'timestamp': fields.Datetime.to_string(fields.Datetime.now())
            }

        except Exception as e:
            _logger.error(f"Lỗi khi lấy dữ liệu điều phối cho bệnh nhân {patient_id}: {str(e)}")
            return {'success': False, 'message': str(e)}

    @http.route('/coordinator/create_token', type='json', auth='user')
    def create_priority_token(self, patient_id, service_id, room_id=None, notes=''):
        """Tạo token ưu tiên cho bệnh nhân"""
        try:
            patient = request.env['res.partner'].browse(patient_id)
            service = request.env['queue.service'].browse(service_id)

            if not all([patient.exists(), service.exists()]):
                return {'success': False, 'message': 'Thông tin không hợp lệ'}

            # Nếu không chỉ định phòng, tự động chọn phòng tối ưu
            if not room_id:
                available_rooms = request.env['queue.room'].search([
                    ('service_id', '=', service_id),
                    ('state', '=', 'open')
                ])
                
                if not available_rooms:
                    return {'success': False, 'message': f'Không có phòng khả dụng cho dịch vụ {service.name}'}
                
                # Chọn phòng có thời gian chờ thấp nhất
                optimal_room = min(available_rooms, key=lambda r: r.estimated_wait_time)
                room_id = optimal_room.id

            room = request.env['queue.room'].browse(room_id)
            if not room.exists():
                return {'success': False, 'message': 'Phòng không tồn tại'}

            # Tính toán priority
            base_priority = self._calculate_patient_priority(patient)

            # Tạo token
            token_vals = {
                'patient_id': patient_id,
                'service_id': service_id,
                'room_id': room_id,
                'priority': base_priority + 1,  # Tăng ưu tiên cho token từ điều phối
                'notes': f'Token điều phối: {notes}' if notes else 'Token được tạo bởi điều phối viên',
                'state': 'waiting',
                'service_type': 'regular'
            }

            token = request.env['queue.token'].sudo().create(token_vals)

            return {
                'success': True,
                'message': f'Đã tạo token {token.name} cho dịch vụ {service.name} tại {room.name}',
                'token_id': token.id
            }

        except Exception as e:
            _logger.error(f"Lỗi khi tạo token điều phối: {str(e)}")
            return {'success': False, 'message': str(e)}

    def _calculate_patient_priority(self, patient):
        """Tính toán mức ưu tiên cho bệnh nhân"""
        priority = 0
        
        if patient.age >= 65:
            priority = max(priority, 1)
        if patient.is_pregnant or patient.is_disabled:
            priority = max(priority, 2)
        if patient.has_urgent_condition:
            priority = max(priority, 3)
        if patient.is_vip:
            priority = max(priority, 4)
        if patient.doctor_assigned_priority:
            priority = max(priority, 5)
            
        return priority

    @http.route('/coordinator/move_token', type='json', auth='user')
    def move_token_to_room(self, token_id, new_room_id, reason=''):
        """Di chuyển token sang phòng khác"""
        try:
            token = request.env['queue.token'].browse(token_id)
            new_room = request.env['queue.room'].browse(new_room_id)

            if not token.exists() or not new_room.exists():
                return {'success': False, 'message': 'Token hoặc phòng không tồn tại'}

            # Kiểm tra phòng mới có thể thực hiện dịch vụ này không
            if new_room.service_id.id != token.service_id.id:
                return {
                    'success': False, 
                    'message': f'Phòng {new_room.name} không thể thực hiện dịch vụ {token.service_id.name}'
                }

            old_room_name = token.room_id.name if token.room_id else 'Chưa có'
            token.sudo().write({'room_id': new_room_id})

            # Sắp xếp lại hàng đợi
            token._add_to_queue_and_sort()

            # Ghi log
            message = f"Token được chuyển từ {old_room_name} sang {new_room.name}"
            if reason:
                message += f". Lý do: {reason}"

            token.message_post(
                body=message,
                subject="Chuyển phòng bởi điều phối viên"
            )

            return {
                'success': True,
                'message': f'Đã chuyển token {token.name} sang {new_room.name}'
            }

        except Exception as e:
            _logger.error(f"Lỗi khi chuyển token: {str(e)}")
            return {'success': False, 'message': str(e)}

    @http.route('/coordinator/optimize_patient_flow', type='json', auth='user')
    def optimize_patient_flow(self, patient_id):
        """Tối ưu luồng bệnh nhân"""
        try:
            patient = request.env['res.partner'].browse(patient_id)

            if not patient.exists() or not patient.is_patient:
                return {'success': False, 'message': 'Bệnh nhân không tồn tại'}

            # Lấy các token đang chờ của bệnh nhân
            waiting_tokens = patient.queue_history_ids.filtered(
                lambda t: t.state in ['draft', 'waiting']
            )

            if not waiting_tokens:
                return {'success': False, 'message': 'Không có token nào cần tối ưu'}

            # Tối ưu từng token
            optimized_tokens = []
            for token in waiting_tokens:
                optimal_room = self._find_optimal_room_for_token(token)
                if optimal_room and optimal_room.id != token.room_id.id:
                    old_room = token.room_id.name if token.room_id else 'Chưa có'
                    old_wait_time = token.room_id.estimated_wait_time if token.room_id else 0
                    
                    token.sudo().write({'room_id': optimal_room.id})
                    token._add_to_queue_and_sort()
                    
                    time_saved = max(0, old_wait_time - optimal_room.estimated_wait_time)

                    optimized_tokens.append({
                        'token_name': token.name,
                        'service_name': token.service_id.name,
                        'old_room': old_room,
                        'new_room': optimal_room.name,
                        'estimated_time_saved': time_saved
                    })

            if not optimized_tokens:
                return {'success': False, 'message': 'Không tìm thấy cách tối ưu nào tốt hơn'}

            return {
                'success': True,
                'message': f'Đã tối ưu {len(optimized_tokens)} token',
                'optimized_tokens': optimized_tokens
            }

        except Exception as e:
            _logger.error(f"Lỗi khi tối ưu luồng bệnh nhân: {str(e)}")
            return {'success': False, 'message': str(e)}

    def _find_optimal_room_for_token(self, token):
        """Tìm phòng tối ưu cho token"""
        available_rooms = request.env['queue.room'].search([
            ('service_id', '=', token.service_id.id),
            ('state', '=', 'open')
        ])

        if not available_rooms:
            return None

        # Chọn phòng có thời gian chờ thấp nhất
        return min(available_rooms, key=lambda r: r.estimated_wait_time)

    @http.route('/coordinator/get_room_status', type='json', auth='user')
    def get_room_status(self, service_id=None):
        """Lấy trạng thái các phòng"""
        try:
            domain = [('state', '=', 'open')]
            if service_id:
                domain.append(('service_id', '=', service_id))

            rooms = request.env['queue.room'].search(domain)
            room_status = []

            for room in rooms:
                waiting_tokens = request.env['queue.token'].search([
                    ('room_id', '=', room.id),
                    ('state', '=', 'waiting')
                ])

                in_progress_tokens = request.env['queue.token'].search([
                    ('room_id', '=', room.id),
                    ('state', '=', 'in_progress')
                ])

                room_status.append({
                    'room_id': room.id,
                    'room_name': room.name,
                    'room_code': room.code,
                    'service_name': room.service_id.name,
                    'capacity': room.capacity,
                    'waiting_count': len(waiting_tokens),
                    'in_progress_count': len(in_progress_tokens),
                    'estimated_wait_time': room.estimated_wait_time,
                    'load_percentage': (len(waiting_tokens) / room.capacity * 100) if room.capacity > 0 else 100,
                    'status': 'overloaded' if len(waiting_tokens) > room.capacity else 'normal'
                })

            return {
                'success': True,
                'rooms': room_status
            }

        except Exception as e:
            _logger.error(f"Lỗi khi lấy trạng thái phòng: {str(e)}")
            return {'success': False, 'message': str(e)}