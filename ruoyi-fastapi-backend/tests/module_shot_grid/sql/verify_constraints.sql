\set ON_ERROR_STOP on

begin;

do $shot_grid_constraints$
declare
    test_project_id bigint;
    test_episode_id bigint;
    test_scene_id bigint;
    test_shot_id bigint;
    test_asset_id bigint;
    test_task_id bigint;
    test_submission_1_id bigint;
    test_submission_2_id bigint;
    test_version_1_id bigint;
    test_version_2_id bigint;
    test_manual_review_list_id bigint;
    test_file_id varchar(36) := '00000000-0000-0000-0000-000000000001';
begin
    insert into sg_project (
        project_code, project_name, create_time, update_time
    ) values (
        'SGTEST', 'Shot Grid约束测试', current_timestamp, current_timestamp
    ) returning project_id into test_project_id;

    insert into sg_project_member (
        project_id, user_id, project_role, producer_code, joined_time, create_time
    ) values (
        test_project_id, 1, 'director', 'ADMIN', current_timestamp, current_timestamp
    );

    begin
        insert into sg_task (
            project_id, task_name, task_kind, assignee_user_id, create_time, update_time
        ) values (
            test_project_id, '无归属任务', 'shot_video', 1, current_timestamp, current_timestamp
        );
        raise exception 'ck_sg_task_owner_kind 未拒绝无归属任务';
    exception
        when check_violation then null;
    end;

    insert into sg_episode (
        project_id, episode_no, storage_dir_name, create_time, update_time
    ) values (
        test_project_id, 1, 'EP01', current_timestamp, current_timestamp
    ) returning episode_id into test_episode_id;

    begin
        insert into sg_scene (
            project_id, episode_id, scene_no, scene_name, create_time, update_time
        ) values (
            test_project_id, test_episode_id, 0, null, current_timestamp, current_timestamp
        );
        raise exception 'ck_sg_scene_prologue_name 未拒绝空名称的序场次';
    exception
        when check_violation then null;
    end;

    insert into sg_scene (
        project_id, episode_id, scene_no, scene_name, create_time, update_time
    ) values (
        test_project_id, test_episode_id, 1, '第一场', current_timestamp, current_timestamp
    ) returning scene_id into test_scene_id;

    insert into sg_shot (
        project_id, episode_id, scene_id, shot_no, storage_dir_name,
        description, create_time, update_time
    ) values (
        test_project_id, test_episode_id, test_scene_id, 1, 'S001',
        '约束测试镜头', current_timestamp, current_timestamp
    ) returning shot_id into test_shot_id;

    insert into sg_task (
        project_id, shot_id, task_name, task_kind, assignee_user_id,
        create_time, update_time
    ) values (
        test_project_id, test_shot_id, '镜头任务', 'shot_video', 1,
        current_timestamp, current_timestamp
    ) returning task_id into test_task_id;

    begin
        insert into sg_task (
            project_id, shot_id, task_name, task_kind, assignee_user_id,
            create_time, update_time
        ) values (
            test_project_id, test_shot_id, '重复镜头任务', 'shot_video', 1,
            current_timestamp, current_timestamp
        );
        raise exception 'uk_sg_task_shot 未拒绝同镜头重复任务';
    exception
        when unique_violation then null;
    end;

    insert into sg_asset (
        project_id, asset_name, asset_name_key, asset_type, storage_dir_name,
        storage_path_key, create_time, update_time
    ) values (
        test_project_id, '测试场景', '测试场景', 'Environment', '测试场景',
        'environment/测试场景', current_timestamp, current_timestamp
    ) returning asset_id into test_asset_id;

    begin
        insert into sg_asset_item (
            project_id, asset_id, production_item, production_item_key,
            create_time, update_time
        ) values (
            test_project_id, test_asset_id, null, '孤立规范键',
            current_timestamp, current_timestamp
        );
        raise exception 'ck_sg_asset_item_name_key 未拒绝空名称和非空规范键';
    exception
        when check_violation then null;
    end;

    insert into sys_file_info (
        file_id, original_name, stored_name, storage_key, file_hash,
        create_time, update_time
    ) values (
        test_file_id, 'source.mp4', 'source.mp4', 'shot-grid-test/source.mp4',
        repeat('a', 64), current_timestamp, current_timestamp
    );

    insert into sg_version_submission (
        project_id, task_id, source_file_id, reserved_version_no, generated_at_ms,
        business_file_name, target_relative_path, temporary_relative_path,
        source_sha256, source_file_size, changelog, submission_status,
        submitted_by, idempotency_key, create_time, update_time
    ) values (
        test_project_id, test_task_id, test_file_id, 1, 1786094626499,
        'SGTEST_EP001_001_S001_ADMIN_V001_1786094626499.mp4',
        'VIDEO/EP01/S001/v001.mp4', 'VIDEO/EP01/S001/.sgtmp-1.part',
        repeat('a', 64), 1, '首版', 'committed',
        1, 'constraint-test-v1', current_timestamp, current_timestamp
    ) returning submission_id into test_submission_1_id;

    insert into sg_version (
        project_id, task_id, submission_id, version_no, changelog,
        submitted_by, submitted_time, generated_at_ms
    ) values (
        test_project_id, test_task_id, test_submission_1_id, 1, '首版',
        1, current_timestamp, 1786094626499
    ) returning version_id into test_version_1_id;

    insert into sg_version_submission (
        project_id, task_id, source_file_id, reserved_version_no, generated_at_ms,
        business_file_name, target_relative_path, temporary_relative_path,
        source_sha256, source_file_size, changelog, submission_status,
        submitted_by, idempotency_key, create_time, update_time
    ) values (
        test_project_id, test_task_id, test_file_id, 2, 1786094626500,
        'SGTEST_EP001_001_S001_ADMIN_V002_1786094626500.mp4',
        'VIDEO/EP01/S001/v002.mp4', 'VIDEO/EP01/S001/.sgtmp-2.part',
        repeat('b', 64), 1, '第二版', 'committed',
        1, 'constraint-test-v2', current_timestamp, current_timestamp
    ) returning submission_id into test_submission_2_id;

    begin
        insert into sg_version (
            project_id, task_id, submission_id, version_no, changelog,
            submitted_by, submitted_time, generated_at_ms
        ) values (
            test_project_id, test_task_id, test_submission_2_id, 1, '重复版本号',
            1, current_timestamp, 1786094626500
        );
        raise exception 'uk_sg_version_task_no 未拒绝重复版本号';
    exception
        when unique_violation then null;
    end;

    insert into sg_version (
        project_id, task_id, submission_id, version_no, changelog,
        submitted_by, submitted_time, generated_at_ms
    ) values (
        test_project_id, test_task_id, test_submission_2_id, 2, '第二版',
        1, current_timestamp, 1786094626500
    ) returning version_id into test_version_2_id;

    insert into sg_review_list (
        project_id, auto_version_id, review_list_name, review_mode, review_status,
        create_time, update_time
    ) values (
        test_project_id, test_version_1_id, 'V001自动审核单', 'auto_single', 'active',
        current_timestamp, current_timestamp
    );

    begin
        insert into sg_review_list (
            project_id, auto_version_id, review_list_name, review_mode, review_status,
            create_time, update_time
        ) values (
            test_project_id, test_version_1_id, '重复自动审核单', 'auto_single', 'active',
            current_timestamp, current_timestamp
        );
        raise exception 'uk_sg_review_list_auto_version 未拒绝重复自动审核单';
    exception
        when unique_violation then null;
    end;

    insert into sg_review_list (
        project_id, review_list_name, review_mode, review_status, create_time, update_time
    ) values (
        test_project_id, '人工批量审核单', 'manual_batch', 'draft', current_timestamp, current_timestamp
    ) returning review_list_id into test_manual_review_list_id;

    insert into sg_review_list_version (
        review_list_id, version_id, sort_order, create_time
    ) values (
        test_manual_review_list_id, test_version_1_id, 0, current_timestamp
    );

    begin
        insert into sg_review_list_version (
            review_list_id, version_id, sort_order, create_time
        ) values (
            test_manual_review_list_id, test_version_2_id, 0, current_timestamp
        );
        raise exception 'uk_sg_review_list_version_sort 未拒绝重复审核顺序';
    exception
        when unique_violation then null;
    end;

    begin
        insert into sg_version_file (
            version_id, file_id, file_role, business_file_name,
            is_primary, create_time
        ) values (
            test_version_1_id, test_file_id, 'thumbnail', 'invalid-primary.jpg',
            '1', current_timestamp
        );
        raise exception 'ck_sg_version_file_primary_role 未拒绝非审核媒体主文件';
    exception
        when check_violation then null;
    end;

    raise notice 'Shot Grid 数据库约束验证通过';
end;
$shot_grid_constraints$;

rollback;
