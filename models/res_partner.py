# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date
import json
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_patient = fields.Boolean(string='Là Bệnh Nhân', default=False)
    date_of_birth = fields.Date(string='Ngày Sinh')
    age = fields.Integer(string='Tuổi', compute='_compute_age', store=True)
    gender = fields.Selection([
        ('male', 'Nam'),
        ('female', 'Nữ'),
        ('other', 'Khác')
    ], string='Giới Tính')
    is_pregnant = fields.Boolean(string='Mang Thai', default=False)
    is_disabled = fields.Boolean(string='Khuyết Tật', default=False)
    has_urgent_condition = fields.Boolean(string='Tình Trạng Cấp Thiết', default=False)
    is_vip = fields.Boolean(string='VIP', default=False)
    doctor_assigned_priority = fields.Boolean(string='Ưu Tiên Chỉ Định Bác Sĩ', default=False)
    queue_package_id = fields.Many2one('queue.package', string='Gói Khám Sức Khỏe')
    queue_history_ids = fields.One2many('queue.token', 'patient_id', string='Lịch Sử Khám')
    queue_history_count = fields.Integer(string='Số lượng token', compute='_compute_queue_history_count')
    current_service_group_id = fields.Many2one('queue.service.group', string='Nhóm Dịch Vụ Hiện Tại')
    completed_service_ids = fields.Many2many(
        'queue.service',
        'partner_completed_service_rel',
        'partner_id',
        'service_id',
        string='Dịch Vụ Đã Hoàn Thành'
    )

    # Các trường mới cho danh sách bệnh nhân
    patient_category = fields.Selection([
        ('vvip', 'VVIP'),
        ('vip', 'VIP'),
        ('normal', 'KH thường'),
        ('child', 'Trẻ em'),
        ('pregnant', 'Thai phụ'),
        ('elderly', 'Người già'),
        ('nccvcm', 'NCCVCM'),
    ], string='Đối tượng', default='normal')

    patient_id_number = fields.Char(string='PID', help="Patient ID Number")

    # Các trường computed
    exam_count = fields.Char(string='Xét nghiệm', compute='_compute_exam_progress', store=False)
    imaging_count = fields.Char(string='CĐHA', compute='_compute_imaging_progress', store=False)
    specialty_count = fields.Char(string='Chuyên khoa', compute='_compute_specialty_progress', store=False)
    estimated_time = fields.Char(string='Thời gian đợi', compute='_compute_estimated_time', store=False)

    # Thêm các computed fields mới
    next_service_recommendations = fields.Text(
        string='Dịch vụ tiếp theo đề xuất',
        compute='_compute_next_service_recommendations',
        store=False
    )

    next_priority_services = fields.Text(
        string='Dịch vụ ưu tiên tiếp theo',
        compute='_compute_next_priority_services',
        store=False
    )

    current_active_token_id = fields.Many2one(
        'queue.token',
        string='Token đang hoạt động',
        compute='_compute_current_active_token',
        store=False
    )

    def _get_priority_services_data(self, partner):
        """Lấy dữ liệu dịch vụ ưu tiên"""
        priority_services = []

        if not partner.is_patient:
            return priority_services

        # Lấy vị trí hiện tại của bệnh nhân
        current_room = self._get_current_patient_location(partner)

        # Lấy danh sách dịch vụ có thể thực hiện
        available_services = self._get_available_services_for_priority(partner)

        # Tính toán điểm ưu tiên cho mỗi dịch vụ
        for service in available_services:
            rooms = self.env['queue.room'].search([
                ('service_id', '=', service['service_id']),
                ('state', '=', 'open')
            ])

            for room in rooms:
                priority_score = self._calculate_priority_score(
                    partner, service, room, current_room
                )

                priority_services.append({
                    'service_id': service['service_id'],
                    'service_name': service['service_name'],
                    'service_code': service['service_code'],
                    'room_id': room.id,
                    'room_name': room.name,
                    'room_code': room.code,
                    'waiting_count': room.queue_length,
                    'estimated_wait_time': room.estimated_wait_time,
                    'travel_time': self._get_travel_time(current_room, room),
                    'priority_score': priority_score,
                    'load_percentage': (room.queue_length / room.capacity * 100) if room.capacity > 0 else 100
                })

        # Sắp xếp theo điểm ưu tiên (thấp hơn = ưu tiên cao hơn)
        priority_services.sort(key=lambda x: x['priority_score'])

        return priority_services[:10]  # Top 10

    def _get_available_services_for_priority(self, partner):
        """Lấy các dịch vụ có thể thực hiện cho priority calculation"""
        services = []

        # Lấy từ recommendations trước
        recommendations_json = partner.next_service_recommendations
        if recommendations_json:
            try:
                recommendations = json.loads(recommendations_json) if isinstance(recommendations_json, str) else []
                for rec in recommendations:
                    if isinstance(rec, dict):
                        services.append({
                            'service_id': rec.get('service_id'),
                            'service_name': rec.get('service_name', ''),
                            'service_code': rec.get('service_code', ''),
                            'estimated_duration': rec.get('estimated_duration', 15)
                        })
            except (json.JSONDecodeError, TypeError):
                pass

        # Nếu không có từ recommendations, lấy từ gói dịch vụ
        if not services and partner.queue_package_id:
            for service in partner.queue_package_id.service_ids:
                if service not in partner.completed_service_ids:
                    services.append({
                        'service_id': service.id,
                        'service_name': service.name,
                        'service_code': service.code,
                        'estimated_duration': service.average_duration
                    })

        return services

    def _get_current_patient_location(self, partner):
        """Lấy vị trí hiện tại của bệnh nhân"""
        # Tìm token đang thực hiện hoặc token hoàn thành gần nhất
        recent_token = partner.queue_history_ids.filtered(
            lambda t: t.state in ['in_progress', 'completed']
        ).sorted('write_date', reverse=True)

        if recent_token and recent_token[0].room_id:
            return recent_token[0].room_id

        return False

    def _calculate_priority_score(self, partner, service, room, current_room):
        """Tính điểm ưu tiên cho phòng"""
        # Trọng số
        WEIGHT_MOVEMENT = 0.4
        WEIGHT_WAITING = 0.35
        WEIGHT_DURATION = 0.15
        WEIGHT_MEDICAL = 0.1

        # Tính điểm di chuyển
        travel_time = self._get_travel_time(current_room, room)
        movement_score = travel_time / 5  # Chuẩn hóa 0-10

        # Tính điểm thời gian chờ
        waiting_score = room.estimated_wait_time / 10  # Chuẩn hóa 0-10

        # Tính điểm thời gian thực hiện
        duration_score = service.get('estimated_duration', 15) / 10  # Chuẩn hóa 0-10

        # Tính điểm ưu tiên y tế
        medical_priority = {
            'BLOOD': 1,
            'XRAY': 3,
            'ULTRA': 4,
            'DOC': 2,
            'VITAL': 5,
            'REG': 10
        }
        med_score = medical_priority.get(service.get('service_code', ''), 5)

        # Tổng điểm
        total_score = (
            WEIGHT_MOVEMENT * movement_score +
            WEIGHT_WAITING * waiting_score +
            WEIGHT_DURATION * duration_score +
            WEIGHT_MEDICAL * med_score
        )

        return total_score

    def _get_travel_time(self, from_room, to_room):
        """Lấy thời gian di chuyển giữa các phòng"""
        if not from_room or not to_room:
            return 5  # Mặc định 5 phút

        if from_room.id == to_room.id:
            return 0

        # Tìm trong bảng khoảng cách
        distance = self.env['queue.room.distance'].search([
            '|',
            '&', ('room_from_id', '=', from_room.id), ('room_to_id', '=', to_room.id),
            '&', ('room_from_id', '=', to_room.id), ('room_to_id', '=', from_room.id)
        ], limit=1)

        if distance:
            return distance.travel_time

        return 5  # Mặc định 5 phút

    def _check_group_completion(self, partner, group):
        """Kiểm tra xem nhóm dịch vụ đã hoàn thành chưa"""
        if not group:
            return False

        completed_services = partner.completed_service_ids
        group_services = group.service_ids

        if group.completion_policy == 'all':
            return all(service in completed_services for service in group_services)
        elif group.completion_policy == 'any':
            return any(service in completed_services for service in group_services)
        else:  # custom
            # Implement custom logic here
            return False

    def _get_next_group(self, partner, current_group):
        """Lấy nhóm dịch vụ tiếp theo"""
        routes = self.env['queue.service.group.route'].search([
            ('group_from_id', '=', current_group.id)
        ], order='sequence')

        # Tìm route phù hợp với gói khám
        if partner.queue_package_id:
            package_routes = routes.filtered(
                lambda r: r.package_id and r.package_id.id == partner.queue_package_id.id
            )
            if package_routes:
                return package_routes[0].group_to_id

        # Tìm route chung
        general_routes = routes.filtered(lambda r: not r.package_id)
        if general_routes:
            return general_routes[0].group_to_id

        return False

    def _get_first_group(self, partner):
        """Lấy nhóm dịch vụ đầu tiên"""
        # Tìm nhóm có sequence thấp nhất
        groups = self.env['queue.service.group'].search([], order='sequence')
        return groups[0] if groups else False

    def _get_services_for_group(self, partner, group):
        """Lấy danh sách dịch vụ cho nhóm"""
        services = []
        for service in group.service_ids:
            # Kiểm tra xem dịch vụ đã hoàn thành chưa
            if service not in partner.completed_service_ids:
                rooms = self.env['queue.room'].search([
                    ('service_id', '=', service.id),
                    ('state', '=', 'open')
                ])

                available_rooms = []
                for room in rooms:
                    available_rooms.append({
                        'room_id': room.id,
                        'room_name': room.name,
                        'room_code': room.code,
                        'waiting_count': room.queue_length,
                        'estimated_wait_time': room.estimated_wait_time,
                        'load_percentage': (room.queue_length / room.capacity * 100) if room.capacity > 0 else 100
                    })

                services.append({
                    'service_id': service.id,
                    'service_name': service.name,
                    'service_code': service.code,
                    'group_id': group.id,
                    'group_name': group.name,
                    'estimated_duration': service.average_duration,
                    'available_rooms': available_rooms,
                    'is_parallel': len(group.service_ids) > 1
                })

        return services

    def _get_pending_services_in_group(self, partner, group):
        """Lấy các dịch vụ chưa hoàn thành trong nhóm"""
        return self._get_services_for_group(partner, group)

    @api.depends('current_service_group_id', 'completed_service_ids', 'queue_history_ids')
    def _compute_next_service_recommendations(self):
        """Tính toán dịch vụ tiếp theo dựa trên nhóm dịch vụ và tiến trình"""
        for partner in self:
            if not partner.is_patient:
                partner.next_service_recommendations = ''
                continue

            # Lấy dữ liệu dịch vụ tiếp theo
            recommendations = self._get_next_services_data(partner)
            
            # Trả về JSON string thay vì HTML
            import json
            partner.next_service_recommendations = json.dumps(recommendations)

    @api.depends('queue_history_ids')
    def _compute_next_priority_services(self):
        """Tính toán dịch vụ ưu tiên dựa trên thời gian chờ và khoảng cách"""
        for partner in self:
            if not partner.is_patient:
                partner.next_priority_services = ''
                continue

            # Lấy dữ liệu dịch vụ ưu tiên
            priority_services = self._get_priority_services_data(partner)
            
            # Trả về JSON string thay vì HTML
            import json
            partner.next_priority_services = json.dumps(priority_services)

    def _get_next_services_data(self, partner):
        """Lấy dữ liệu dịch vụ tiếp theo"""
        recommendations = []

        # Lấy nhóm dịch vụ hiện tại
        current_group = partner.current_service_group_id

        if current_group:
            # Kiểm tra xem nhóm hiện tại đã hoàn thành chưa
            group_completed = self._check_group_completion(partner, current_group)

            if group_completed:
                # Tìm nhóm tiếp theo
                next_group = self._get_next_group(partner, current_group)
                if next_group:
                    recommendations = self._get_services_for_group(partner, next_group)
            else:
                # Lấy các dịch vụ chưa hoàn thành trong nhóm hiện tại
                recommendations = self._get_pending_services_in_group(partner, current_group)
        else:
            # Nếu chưa có nhóm, tìm nhóm đầu tiên
            first_group = self._get_first_group(partner)
            if first_group:
                recommendations = self._get_services_for_group(partner, first_group)

        return recommendations

    def action_view_current_token(self):
        """Xem token hiện tại"""
        self.ensure_one()
        if self.current_active_token_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Token hiện tại',
                'res_model': 'queue.token',
                'res_id': self.current_active_token_id.id,
                'view_mode': 'form',
                'target': 'new',
            }

    @api.depends('queue_history_ids')
    def _compute_current_active_token(self):
        """Tìm token đang hoạt động của bệnh nhân"""
        for partner in self:
            active_token = partner.queue_history_ids.filtered(
                lambda t: t.state in ['waiting', 'in_progress']
            ).sorted('create_date', reverse=True)

            partner.current_active_token_id = active_token[0] if active_token else False

    def _check_group_completion(self, partner, group):
        """Kiểm tra xem nhóm dịch vụ đã hoàn thành chưa"""
        if not group:
            return False

        completed_services = partner.completed_service_ids
        group_services = group.service_ids

        if group.completion_policy == 'all':
            return all(service in completed_services for service in group_services)
        elif group.completion_policy == 'any':
            return any(service in completed_services for service in group_services)
        else:  # custom
            # Implement custom logic here
            return False

    def _get_next_group(self, partner, current_group):
        """Lấy nhóm dịch vụ tiếp theo"""
        routes = self.env['queue.service.group.route'].search([
            ('group_from_id', '=', current_group.id)
        ], order='sequence')

        # Tìm route phù hợp với gói khám
        if partner.queue_package_id:
            package_routes = routes.filtered(
                lambda r: r.package_id.id == partner.queue_package_id.id
            )
            if package_routes:
                return package_routes[0].group_to_id

        # Tìm route chung
        general_routes = routes.filtered(lambda r: not r.package_id)
        if general_routes:
            return general_routes[0].group_to_id

        return False

    def _get_first_group(self, partner):
        """Lấy nhóm dịch vụ đầu tiên"""
        # Tìm nhóm có sequence thấp nhất
        groups = self.env['queue.service.group'].search([], order='sequence')
        return groups[0] if groups else False

    def _get_services_for_group(self, partner, group):
        """Lấy danh sách dịch vụ cho nhóm"""
        services = []
        for service in group.service_ids:
            # Kiểm tra xem dịch vụ đã hoàn thành chưa
            if service not in partner.completed_service_ids:
                rooms = self.env['queue.room'].search([
                    ('service_id', '=', service.id),
                    ('state', '=', 'open')
                ])

                available_rooms = []
                for room in rooms:
                    available_rooms.append({
                        'room_id': room.id,
                        'room_name': room.name,
                        'room_code': room.code,
                        'waiting_count': room.queue_length,
                        'estimated_wait_time': room.estimated_wait_time,
                        'load_percentage': (room.queue_length / room.capacity * 100) if room.capacity > 0 else 100
                    })

                services.append({
                    'service_id': service.id,
                    'service_name': service.name,
                    'service_code': service.code,
                    'group_id': group.id,
                    'group_name': group.name,
                    'estimated_duration': service.average_duration,
                    'available_rooms': available_rooms,
                    'is_parallel': len(group.service_ids) > 1
                })

        return services

    def _get_pending_services_in_group(self, partner, group):
        """Lấy các dịch vụ chưa hoàn thành trong nhóm"""
        return self._get_services_for_group(partner, group)

    def _get_current_patient_location(self, partner):
        """Lấy vị trí hiện tại của bệnh nhân"""
        # Tìm token đang thực hiện hoặc token hoàn thành gần nhất
        recent_token = partner.queue_history_ids.filtered(
            lambda t: t.state in ['in_progress', 'completed']
        ).sorted('write_date', reverse=True)

        if recent_token and recent_token[0].room_id:
            return recent_token[0].room_id

        return False

    def _get_available_services(self, partner):
        """Lấy tất cả dịch vụ có thể thực hiện"""
        services = []

        # Lấy từ recommendations
        if partner.next_service_recommendations:
            try:
                recommendations = json.loads(partner.next_service_recommendations)
                services.extend(recommendations)
            except:
                pass

        # Lấy các dịch vụ khác nếu cần
        # ...

        return services

    def _calculate_priority_score(self, partner, service, room, current_room):
        """Tính điểm ưu tiên cho phòng"""
        # Trọng số
        WEIGHT_MOVEMENT = 0.4
        WEIGHT_WAITING = 0.35
        WEIGHT_DURATION = 0.15
        WEIGHT_MEDICAL = 0.1

        # Tính điểm di chuyển
        travel_time = self._get_travel_time(current_room, room)
        movement_score = travel_time / 5  # Chuẩn hóa 0-10

        # Tính điểm thời gian chờ
        waiting_score = room.estimated_wait_time / 10  # Chuẩn hóa 0-10

        # Tính điểm thời gian thực hiện
        duration_score = service.get('estimated_duration', 15) / 10  # Chuẩn hóa 0-10

        # Tính điểm ưu tiên y tế
        medical_priority = {
            'BLOOD': 1,
            'XRAY': 3,
            'ULTRA': 4,
            'DOC': 2,
            'VITAL': 5,
            'REG': 10
        }
        med_score = medical_priority.get(service.get('service_code', ''), 5)

        # Tổng điểm
        total_score = (
            WEIGHT_MOVEMENT * movement_score +
            WEIGHT_WAITING * waiting_score +
            WEIGHT_DURATION * duration_score +
            WEIGHT_MEDICAL * med_score
        )

        return total_score

    def _get_travel_time(self, from_room, to_room):
        """Lấy thời gian di chuyển giữa các phòng"""
        if not from_room or not to_room:
            return 5  # Mặc định 5 phút

        if from_room.id == to_room.id:
            return 0

        # Tìm trong bảng khoảng cách
        distance = self.env['queue.room.distance'].search([
            '|',
            '&', ('room_from_id', '=', from_room.id), ('room_to_id', '=', to_room.id),
            '&', ('room_from_id', '=', to_room.id), ('room_to_id', '=', from_room.id)
        ], limit=1)

        if distance:
            return distance.travel_time

        return 5  # Mặc định 5 phút

    @api.depends('date_of_birth')
    def _compute_age(self):
        """Tính tuổi từ ngày sinh"""
        for partner in self:
            if partner.date_of_birth:
                today = date.today()
                born = partner.date_of_birth
                partner.age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
            else:
                partner.age = 0

    @api.depends('queue_history_ids')
    def _compute_queue_history_count(self):
        """Đếm số lượng token đã cấp cho bệnh nhân"""
        for partner in self:
            partner.queue_history_count = len(partner.queue_history_ids)

    def _compute_exam_progress(self):
        """Tính tiến độ xét nghiệm"""
        for partner in self:
            if partner.is_patient and partner.queue_history_ids:
                exam_tokens = partner.queue_history_ids.filtered(
                    lambda t: t.service_id.service_type == 'lab'
                )
                completed = exam_tokens.filtered(lambda t: t.state == 'completed')
                total = len(exam_tokens)
                completed_count = len(completed)
                partner.exam_count = f"{completed_count}/{total}" if total > 0 else "1/3"
            else:
                partner.exam_count = "1/3"

    def _compute_imaging_progress(self):
        """Tính tiến độ chẩn đoán hình ảnh"""
        for partner in self:
            if partner.is_patient and partner.queue_history_ids:
                imaging_tokens = partner.queue_history_ids.filtered(
                    lambda t: t.service_id.service_type == 'imaging'
                )
                completed = imaging_tokens.filtered(lambda t: t.state == 'completed')
                total = len(imaging_tokens)
                completed_count = len(completed)
                partner.imaging_count = f"{completed_count}/{total}" if total > 0 else "1/7"
            else:
                partner.imaging_count = "1/7"

    def _compute_specialty_progress(self):
        """Tính tiến độ chuyên khoa"""
        for partner in self:
            if partner.is_patient and partner.queue_history_ids:
                specialty_tokens = partner.queue_history_ids.filtered(
                    lambda t: t.service_id.service_type in ['consultation', 'specialty']
                )
                completed = specialty_tokens.filtered(lambda t: t.state == 'completed')
                total = len(specialty_tokens)
                completed_count = len(completed)
                partner.specialty_count = f"{completed_count}/{total}" if total > 0 else "2/6"
            else:
                partner.specialty_count = "2/6"

    def action_back(self):
        """Quay lại danh sách bệnh nhân"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Danh sách bệnh nhân',
            'res_model': 'res.partner',
            'view_mode': 'kanban,list',
            'domain': [('is_patient', '=', True)],
            'context': {'default_is_patient': True},
            'target': 'current',
        }

    def _compute_estimated_time(self):
        """Tính thời gian đợi ước tính"""
        for partner in self:
            if partner.is_patient and partner.queue_history_ids:
                waiting_token = partner.queue_history_ids.filtered(
                    lambda t: t.state == 'waiting'
                ).sorted('estimated_wait_time')

                if waiting_token:
                    time_minutes = waiting_token[0].estimated_wait_time
                    hours = int(time_minutes // 60)
                    minutes = int(time_minutes % 60)
                    if hours > 0:
                        partner.estimated_time = f"{hours} giờ {minutes} phút"
                    else:
                        partner.estimated_time = f"{minutes} phút"
                else:
                    partner.estimated_time = "1 giờ 12 phút"
            else:
                partner.estimated_time = "1 giờ 12 phút"
