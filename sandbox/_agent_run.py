from reverse_linked_list import ListNode, reverseList

def test_reverseList():
    # Create a linked list: 1 -> 2 -> 3 -> None
    head = ListNode(1)
    head.next = ListNode(2)
    head.next.next = ListNode(3)

    # Reverse the linked list
    reversed_head = reverseList(head)

    # Check if the reversed list is correct: 3 -> 2 -> 1 -> None
    assert reversed_head.val == 3
    assert reversed_head.next.val == 2
    assert reversed_head.next.next.val == 1
    assert reversed_head.next.next.next is None

test_reverseList()